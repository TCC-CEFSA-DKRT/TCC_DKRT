variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_id" {
  description = "Subnet pública onde API, worker e Ollama rodam (fase9.spec.md: sem NAT gateway, ver modules/network)."
  type        = string
}

variable "api_sg_id" {
  type = string
}

variable "worker_sg_id" {
  type = string
}

variable "ollama_sg_id" {
  type = string
}

variable "ami_id" {
  description = "AMI base (Ubuntu 22.04 LTS na região escolhida) para API e worker. Deve ser resolvida no ambiente (data \"aws_ami\") e passada aqui -- este módulo não faz lookup próprio para ficar testável/portável entre regiões."
  type        = string
}

variable "ollama_ami_id" {
  description = <<-DESC
    AMI para a instância Ollama, separada de var.ami_id (adr-0015). Uma AMI
    Ubuntu genérica (como a usada em api/worker) não traz driver
    NVIDIA/CUDA -- numa instância g4dn a GPU ficaria fisicamente presente
    mas inutilizada, e o Ollama rodaria em CPU silenciosamente (o
    instalador do Ollama detecta a GPU via `nvidia-smi` em runtime; sem
    driver, `nvidia-smi` simplesmente não existe e ele não avisa).
    Null (default) cai de volta para var.ami_id, o que só é seguro se
    var.ollama_instance_type também for revertido para uma família sem
    GPU (ex.: t3.large). Ao usar g4dn.xlarge (default de
    ollama_instance_type), o ambiente chamador deve resolver esta AMI via
    data "aws_ami" com o filtro "Deep Learning Base OSS Nvidia Driver GPU
    AMI (Ubuntu 22.04)*", owners = ["amazon"] (ver
    environments/dev/main.tf) e passá-la aqui.
  DESC
  type        = string
  default     = null
}

variable "key_name" {
  description = "Nome do key pair EC2 (SSH) já existente na conta/região. Null desabilita acesso SSH por chave (não recomendado)."
  type        = string
  default     = null
}

variable "api_instance_type" {
  type    = string
  default = "t3.micro"
}

variable "api_root_volume_size" {
  description = "Disco raiz (GB) do host da API. A imagem Docker (torch/sentence-transformers) passa de 3 GB comprimida; os 8 GB padrao da AMI nao comportam o pull."
  type        = number
  default     = 30
}

variable "worker_instance_type" {
  type    = string
  default = "t3.micro"
}

variable "ollama_instance_type" {
  description = <<-DESC
    Instancia para o Ollama. Qwen 2.5 3B/4B (decisao do usuario -- ver
    docs/adr/adr-0013.md). Default GPU (g4dn.xlarge, 1x NVIDIA T4, 16 GiB
    VRAM) desde a adr-0015: o Nivel 2 (SLM) passou a rodar sobre toda
    entidade auditada, nao mais so' ~10% (adr-0014), o que torna o
    throughput de GPU proporcionalmente mais valioso do que quando essa
    variavel apontava para t3.large (CPU). Custo sob demanda em us-east-1
    fica em torno de US$0,53/h: manter a disciplina de start/stop (nunca
    deixar ligado por padrao, ver scripts/start_ollama.sh e
    scripts/stop_ollama.sh).
    Requer var.ollama_ami_id apontando para uma AMI com driver NVIDIA/CUDA
    (ver variable "ollama_ami_id" acima) -- sem isso a GPU fica ociosa e o
    Ollama roda em CPU do mesmo jeito. Trocar de volta para uma familia
    sem GPU (ex.: t3.large, com ollama_ami_id = null) se a familia g4dn
    nao estiver liberada para lancamento na conta --
    confirmar a cota de vCPU de instancias G no console antes do apply.
  DESC
  type        = string
  default     = "g4dn.xlarge"
}

variable "provision_ollama" {
  description = "Se false, não cria a instância Ollama (ex.: ambiente de dev usando Ollama local já em outra máquina)."
  type        = bool
  default     = true
}

# ADR-0017 (producao apenas): API e worker migram para Lambda
# (modules/lambda_compute) -- Ollama continua em EC2 sempre (decisao
# propria, ADR-0013/docs/design/implantacao-aws.html, nao por limitacao de
# conta). Defaults true preservam EXATAMENTE o comportamento atual da
# Academy (nenhum ambiente chamador hoje define estas variaveis) -- so'
# environments/production/main.tf vai passar false explicitamente para as
# duas, depois de trocar para o modulo Lambda.
variable "provision_api" {
  description = "Se false, não cria a instância EC2 da API (produção, ADR-0017: API roda como Lambda)."
  type        = bool
  default     = true
}

variable "provision_worker" {
  description = "Se false, não cria a instância EC2 do worker (produção, ADR-0017: worker roda como Lambda)."
  type        = bool
  default     = true
}

variable "ollama_model" {
  description = "Deve espelhar settings.OLLAMA_MODEL (.env / Settings.ollama_model) para a app apontar para o mesmo modelo já baixado na instância."
  type        = string
  default     = "qwen2.5:3b-instruct"
}

# --- IAM: padrão create_role / existing_role_arn (fase9.spec.md, secao 2.5)
# create_role=true cria role/policy/instance profile com permissões mínimas;
# create_role=false usa um instance profile já existente (nome em
# existing_instance_profile_name).

variable "create_role" {
  description = "true cria role própria com permissões mínimas; false usa o instance profile existente informado em existing_instance_profile_name."
  type        = bool
  default     = true
}

variable "existing_instance_profile_name" {
  description = "Nome do instance profile já existente a usar quando create_role=false."
  type        = string
  default     = null
}

variable "queue_url" {
  type = string
}

variable "queue_arn" {
  type = string
}

variable "database_url_template" {
  type = string
}

variable "orion_credentials_secret_arn" {
  description = <<-DESC
    ARN do segredo do Orion no Secrets Manager (modules/secrets). Null
    (default) omite a statement secretsmanager:GetSecretValue da policy da
    role EC2 (main.tf) -- caso de uso real, ADR-0017: producao passa a usar
    modules/compute so' para o Ollama (API/worker migram para Lambda,
    modules/lambda_compute, que le' esses segredos via Parameter Store,
    modules/parameter_store, nao Secrets Manager), e o Ollama sozinho nao
    precisa de credencial do Orion nem de chave JWT. O ambiente dev
    (EC2) passa um ARN real aqui.
  DESC
  type        = string
  default     = null
}

variable "jwt_signing_key_secret_arn" {
  description = "Ver orion_credentials_secret_arn, acima -- mesmo raciocinio."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "aws_region" {
  description = "Região AWS, usada pelo script de deploy da API (ecr login, secretsmanager)."
  type        = string
  default     = "us-east-1"
}

variable "fiware_broker_url" {
  description = "URL do Orion que a API audita."
  type        = string
  default     = "http://localhost:1026"
}

variable "cors_allowed_origins" {
  description = "Origens permitidas pelo CORS da API (URL do frontend do ambiente)."
  type        = string
  default     = "http://localhost:4200"
}

variable "deployment_mode" {
  description = "ADR-0019: \"selfhosted\" ou \"saas\"."
  type        = string
  default     = "selfhosted"
}

variable "database_host" {
  description = "Endpoint do RDS. A senha vem do Secrets Manager (database_secret_arn) na hora do deploy, nunca do Terraform."
  type        = string
  default     = null
}

variable "database_port" {
  type    = number
  default = 5432
}

variable "database_name" {
  type    = string
  default = "auditor"
}

variable "database_secret_arn" {
  description = "ARN do segredo do RDS (manage_master_user_password). Null omite a permissão na role."
  type        = string
  default     = null
}
