export interface Restaurant {
  id: number
  name: string
  timezone: string
  is_demo: boolean
  tracking_since: string
  latest_day: string | null
}

export interface Table {
  id: number
  name: string
}
export interface Metrics {
  started_visits: number
  completed_visits: number
  duration_samples: number
  contact_samples: number
  average_duration_seconds: number | null
  median_duration_seconds: number | null
  average_first_contact_seconds: number | null
  median_first_contact_seconds: number | null
  late_first_contacts: number
  long_visits: number
  counts: Record<string, number>
  hours: number[]
}
export type DayStatus = 'PROCESSED' | 'UNPROCESSED' | 'INCOMPLETE' | 'CLOSED'
export interface DayReport {
  day: string
  status: DayStatus
  run_status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'WAITING_FOR_INPUT' | null
  historical: boolean
  error: string | null
  schedule: {
    timezone: string
    windows: { opens_at: string; closes_at: string; observed_until: string }[]
    ready_at: string | null
    is_override: boolean
  }
  metrics: Metrics | null
}
export interface VisitEvent {
  id: number
  type: string
  occurred_at: string
  source: string
  review_status: string
  confidence: number | null
  order_id: number | null
}
export interface Visit {
  id: number
  table_id: number
  table_name: string
  operating_date: string
  timezone: string
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  first_contact_seconds: number | null
  events: VisitEvent[]
}
export interface Report {
  start: string
  end: string
  table_id: number | null
  metrics: Metrics | null
  days: DayReport[]
  missing_days: Pick<DayReport, 'day' | 'status'>[]
  tables: (Table & { metrics: Metrics })[]
  visits: Visit[]
}
export type HoursMode = 'closed' | 'intervals' | 'all_day'
export interface DayHours {
  mode: HoursMode
  intervals: { opens: string; closes: string }[]
}
export interface Settings {
  name: string
  timezone: string
  observation_minutes: number
  processing_delay_minutes: number
  weekly_hours: DayHours[]
  overrides: { day: string; hours: DayHours }[]
}

export const apiRoot = '/api/v1'
export const restaurantPath = (id: number) => '/restaurants/' + id

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response
  try {
    response = await fetch(apiRoot + path, init)
  } catch {
    throw new Error('Не удалось подключиться к серверу. Попробуйте ещё раз.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail) && detail[0]?.msg) {
      const message = detail[0].msg.replace(/^Value error, /, '')
      throw new Error(/[А-Яа-я]/.test(message) ? message : 'Проверьте значения в полях формы.')
    }
    throw new Error('Ошибка сервера (' + response.status + '). Попробуйте ещё раз.')
  }
  return response.json()
}
