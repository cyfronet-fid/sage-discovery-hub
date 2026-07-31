import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { IdpListPageComponent } from './idp-list-page.component';

@NgModule({
  declarations: [IdpListPageComponent],
  imports: [
    CommonModule,
    RouterModule.forChild([
      {
        path: '',
        component: IdpListPageComponent,
      },
    ]),
  ],
})
export class IdpListPageModule {}
