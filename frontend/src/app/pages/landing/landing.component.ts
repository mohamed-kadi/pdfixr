import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { JobType } from '../../core/models';

interface LandingFeature {
  operation: JobType;
  title: string;
  subtitle: string;
  description: string;
  outcome: string;
}

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.css',
})
export class LandingComponent implements OnInit, OnDestroy {
  readonly features: LandingFeature[] = [
    {
      operation: 'font_fix',
      title: 'Fix Form Fields',
      subtitle: 'Cross-viewer consistency',
      description:
        'Standardizes form rendering so typed values look consistent across Preview, Chrome, and other PDF viewers.',
      outcome: 'Output: one fixed PDF with normalized fillable form appearance.',
    },
    {
      operation: 'compress',
      title: 'Compress PDF',
      subtitle: 'Faster sharing',
      description: 'Reduces file size while preserving readability for easier upload, delivery, and storage.',
      outcome: 'Output: one smaller PDF optimized for transfer.',
    },
    {
      operation: 'merge',
      title: 'Merge PDFs',
      subtitle: 'Single final document',
      description: 'Combines multiple PDFs into one file using the same order as your selected inputs.',
      outcome: 'Output: one merged PDF.',
    },
    {
      operation: 'split',
      title: 'Split PDF',
      subtitle: 'Range-based exports',
      description: 'Extracts specific page ranges into separate documents for cleaner sharing and organization.',
      outcome: 'Output: ZIP file containing split PDFs.',
    },
  ];

  activeFeatureIndex = 0;
  private carouselTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.startCarousel();
  }

  ngOnDestroy(): void {
    this.stopCarousel();
  }

  nextFeature(): void {
    if (this.features.length === 0) {
      return;
    }
    this.activeFeatureIndex = (this.activeFeatureIndex + 1) % this.features.length;
    this.restartCarousel();
  }

  previousFeature(): void {
    if (this.features.length === 0) {
      return;
    }
    this.activeFeatureIndex = (this.activeFeatureIndex - 1 + this.features.length) % this.features.length;
    this.restartCarousel();
  }

  goToFeature(index: number): void {
    if (index < 0 || index >= this.features.length) {
      return;
    }
    this.activeFeatureIndex = index;
    this.restartCarousel();
  }

  trackByOperation(_: number, feature: LandingFeature): JobType {
    return feature.operation;
  }

  private startCarousel(): void {
    this.stopCarousel();
    this.carouselTimer = setInterval(() => {
      if (this.features.length === 0) {
        return;
      }
      this.activeFeatureIndex = (this.activeFeatureIndex + 1) % this.features.length;
    }, 4800);
  }

  private stopCarousel(): void {
    if (!this.carouselTimer) {
      return;
    }
    clearInterval(this.carouselTimer);
    this.carouselTimer = null;
  }

  private restartCarousel(): void {
    this.startCarousel();
  }
}
