import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {
  AnalyticsRange,
  DeviceBreakdown,
  GeoBreakdown,
  OverviewStats,
  ReferrerBreakdown,
  TimeseriesResponse,
} from '../models/analytics.model';

@Injectable({ providedIn: 'root' })
export class AnalyticsApi {
  private readonly api = inject(ApiService);

  overview(): Observable<OverviewStats> {
    return this.api.get<OverviewStats>('/v1/analytics/overview');
  }

  timeseries(urlId: string, range: AnalyticsRange): Observable<TimeseriesResponse> {
    return this.api.get<TimeseriesResponse>(`/v1/analytics/urls/${urlId}/timeseries`, { range });
  }

  geo(urlId: string, range: AnalyticsRange): Observable<GeoBreakdown[]> {
    return this.api.get<GeoBreakdown[]>(`/v1/analytics/urls/${urlId}/geo`, { range });
  }

  referrers(urlId: string, range: AnalyticsRange): Observable<ReferrerBreakdown[]> {
    return this.api.get<ReferrerBreakdown[]>(`/v1/analytics/urls/${urlId}/referrers`, { range });
  }

  devices(urlId: string, range: AnalyticsRange): Observable<DeviceBreakdown[]> {
    return this.api.get<DeviceBreakdown[]>(`/v1/analytics/urls/${urlId}/devices`, { range });
  }
}
