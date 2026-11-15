import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { DiffViewComponent } from '../../../shared/components/diff-view/diff-view.component';
import { RecommendationView } from '../report-detail.interface';

@Component({
  selector: 'app-recommendation-card',
  standalone: true,
  imports: [DiffViewComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './recommendation-card.component.html',
  styleUrl: './recommendation-card.component.scss',
})
export class RecommendationCardComponent {
  readonly view = input.required<RecommendationView>();
}
