from __future__ import annotations

from pathlib import Path

import pytest

hcl2 = pytest.importorskip("hcl2")

TERRAFORM_ROOT = Path(__file__).resolve().parents[3] / "infra" / "terraform"


def _load(path: Path):
    with path.open() as f:
        return hcl2.load(f)


def _unquote(value):
    if isinstance(value, str):
        return value.strip('"')
    return value


def _find_resource(doc, resource_type, resource_name):
    for block in doc.get("resource", []):
        for typ, instances in block.items():
            if _unquote(typ) == resource_type:
                for name, body in instances.items():
                    if _unquote(name) == resource_name:
                        return body
    return None


def _module_call_args(module_name):
    doc = _load(TERRAFORM_ROOT / "environments" / "production" / "main.tf")
    for block in doc["module"]:
        for name, body in block.items():
            if _unquote(name) == module_name:
                return {
                    key: value
                    for key, value in body.items()
                    if key not in ("__is_block__", "source", "providers")
                }
    raise AssertionError(f"module {module_name!r} nao encontrado em production/main.tf")


def _module_variables(module_dir):
    doc = _load(TERRAFORM_ROOT / "modules" / module_dir / "variables.tf")
    variables = {}
    for block in doc.get("variable", []):
        for name, body in block.items():
            variables[_unquote(name)] = body
    return variables


class TestParameterStoreModule:
    def test_broker_api_key_encryption_keys_parameter_is_a_secure_string_with_ignore_changes(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "parameter_store" / "main.tf")
        resource = _find_resource(doc, "aws_ssm_parameter", "broker_api_key_encryption_keys")

        assert resource is not None
        assert _unquote(resource["type"]) == "SecureString"
        ignore_changes = resource["lifecycle"][0]["ignore_changes"]
        assert "value" in [_unquote(v) for v in ignore_changes]

    def test_outputs_expose_the_new_parameter(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "parameter_store" / "outputs.tf")
        output_names = {
            _unquote(name)
            for block in doc.get("output", [])
            for name in block
        }

        assert "broker_api_key_encryption_keys_parameter_name" in output_names
        assert "broker_api_key_encryption_keys_parameter_arn" in output_names


class TestLambdaComputeModule:
    def test_common_env_carries_deployment_mode_and_broker_keys_parameter_name(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "main.tf")
        common_env = doc["locals"][0]["common_env"]

        assert "DEPLOYMENT_MODE" in common_env
        assert "BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME" in common_env

    def test_common_env_never_carries_a_plaintext_secret(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "main.tf")
        common_env = doc["locals"][0]["common_env"]

        assert "JWT_SIGNING_KEY" not in common_env
        assert "BROKER_API_KEY_ENCRYPTION_KEYS" not in common_env

    def test_iam_policy_grants_ssm_get_parameter_on_the_broker_keys_parameter(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "main.tf")
        policy_body = _find_resource(doc, "aws_iam_role_policy", "lambda_permissions")

        assert "var.broker_api_key_encryption_keys_parameter_arn" in policy_body["policy"]

    def test_deployment_mode_variable_defaults_to_selfhosted(self):
        variables = _module_variables("lambda_compute")

        assert "deployment_mode" in variables
        assert _unquote(variables["deployment_mode"]["default"]) == "selfhosted"


class TestModuleWiringMatchesDeclaredVariables:
    @pytest.mark.parametrize("module_name, module_dir", [("lambda_compute", "lambda_compute"), ("parameter_store", "parameter_store")])
    def test_every_passed_argument_is_a_declared_variable(self, module_name, module_dir):
        variables = _module_variables(module_dir)
        call_args = _module_call_args(module_name)

        for arg_name in call_args:
            assert arg_name in variables, (
                f"production/main.tf passa {arg_name!r} para {module_name!r}, "
                f"mas modules/{module_dir}/variables.tf nao declara essa variable"
            )

    @pytest.mark.parametrize("module_name, module_dir", [("lambda_compute", "lambda_compute"), ("parameter_store", "parameter_store")])
    def test_every_required_variable_is_passed(self, module_name, module_dir):
        variables = _module_variables(module_dir)
        call_args = _module_call_args(module_name)

        for var_name, body in variables.items():
            if "default" not in body:
                assert var_name in call_args, (
                    f"modules/{module_dir}/variables.tf exige {var_name!r} sem default, "
                    f"mas production/main.tf nao passa esse argumento para {module_name!r}"
                )

    def test_lambda_compute_gets_the_new_broker_keys_arguments_wired_from_production(self):
        variables = _module_variables("lambda_compute")
        call_args = _module_call_args("lambda_compute")

        for name in (
            "deployment_mode",
            "broker_api_key_encryption_keys_parameter_name",
            "broker_api_key_encryption_keys_parameter_arn",
        ):
            assert name in variables, f"lambda_compute nao declara a variable {name!r}"
            assert name in call_args, f"production/main.tf nao passa {name!r} para lambda_compute"


class TestAdminLambda:
    def test_admin_function_uses_the_admin_handler_entrypoint(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "main.tf")
        resource = _find_resource(doc, "aws_lambda_function", "admin")

        assert resource is not None
        command = resource["image_config"][0]["command"]
        assert [_unquote(c) for c in command] == ["auditor.interfaces.aws_lambda.admin_handler.handler"]

    def test_admin_function_reuses_the_lambda_sg_private_subnets_and_common_env(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "main.tf")
        resource = _find_resource(doc, "aws_lambda_function", "admin")

        vpc_config = resource["vpc_config"][0]
        assert "aws_security_group.lambda.id" in str(vpc_config["security_group_ids"])
        assert "var.private_subnet_ids" in str(vpc_config["subnet_ids"])
        assert "local.common_env" in str(resource["environment"][0]["variables"])

    def test_no_lambda_permission_function_url_or_event_source_mapping_targets_admin(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "main.tf")

        for block in doc.get("resource", []):
            for typ, instances in block.items():
                if _unquote(typ) not in (
                    "aws_lambda_permission",
                    "aws_lambda_function_url",
                    "aws_lambda_event_source_mapping",
                ):
                    continue
                for body in instances.values():
                    assert "aws_lambda_function.admin" not in str(body), (
                        f"{_unquote(typ)!r} nao deveria referenciar aws_lambda_function.admin"
                    )

    def test_admin_invoke_policy_grants_only_invoke_on_the_admin_function_arn(self):
        doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "main.tf")
        policy = _find_resource(doc, "aws_iam_policy", "admin_invoke")

        assert policy is not None
        policy_text = str(policy["policy"])
        assert "lambda:InvokeFunction" in policy_text
        assert "aws_lambda_function.admin.arn" in policy_text
        assert '"*"' not in policy_text

    def test_module_and_production_outputs_expose_the_admin_function_and_invoke_policy(self):
        module_doc = _load(TERRAFORM_ROOT / "modules" / "lambda_compute" / "outputs.tf")
        module_output_names = {
            _unquote(name) for block in module_doc.get("output", []) for name in block
        }
        production_doc = _load(TERRAFORM_ROOT / "environments" / "production" / "outputs.tf")
        production_output_names = {
            _unquote(name) for block in production_doc.get("output", []) for name in block
        }

        for name in ("admin_function_name", "admin_invoke_policy_arn"):
            assert name in module_output_names, f"lambda_compute/outputs.tf nao expõe {name!r}"
            assert name in production_output_names, f"production/outputs.tf nao expõe {name!r}"

    def test_exactly_one_security_group_rule_still_opens_the_database_sg(self):
        doc = _load(TERRAFORM_ROOT / "environments" / "production" / "main.tf")
        matches = [
            body
            for block in doc.get("resource", [])
            for typ, instances in block.items()
            if _unquote(typ) == "aws_security_group_rule"
            for body in instances.values()
            if "module.network.database_sg_id" in str(body.get("security_group_id"))
        ]

        assert len(matches) == 1
