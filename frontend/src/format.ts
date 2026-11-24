import type { DayStatus } from './api'

export const statusLabels: Record<DayStatus, string> = {
  PROCESSED: 'Обработан',
  UNPROCESSED: 'Не обработан',
  INCOMPLETE: 'Неполные данные',
  CLOSED: 'Выходной',
}

export const eventLabels: Record<string, string> = {
  VISIT_STARTED: 'Посадка гостей',
  WAITER_CONTACT: 'Контакт официанта',
  ORDER_CREATED: 'Заказ зарегистрирован',
  ORDER_UPDATED: 'Заказ изменён',
  FOOD_SERVED: 'Подача блюда',
  DRINK_SERVED: 'Подача напитка',
  BILL_PRESENTED: 'Принесение счёта',
  ORDER_CLOSED: 'Заказ закрыт',
  VISIT_ENDED: 'Окончание посещения',
}

export const sourceLabels: Record<string, string> = {
  DEMO: 'Демо', MANUAL: 'Вручную', VIDEO: 'Видео', R_KEEPER: 'r_keeper',
}
export const reviewLabels: Record<string, string> = {
  PENDING: 'На проверке', CONFIRMED: 'Подтверждено', REJECTED: 'Отклонено',
}

export const number = new Intl.NumberFormat('ru-RU').format

export function dateLabel(day: string, full = false) {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'UTC', day: 'numeric', month: 'short', ...(full ? { year: 'numeric' } : {}),
  }).format(new Date(day + 'T00:00:00Z'))
}

export function at(instant: string, timeZone: string, full = false) {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone, hour: '2-digit', minute: '2-digit',
    ...(full ? { day: 'numeric', month: 'short' } : {}),
  }).format(new Date(instant))
}

export function localToday(timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts()
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type)?.value).join('-')
}

export function shiftDay(day: string, days: number) {
  const time = new Date(day + 'T00:00:00Z')
  time.setUTCDate(time.getUTCDate() + days)
  return time.toISOString().slice(0, 10)
}

export function duration(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  const rounded = Math.round(seconds)
  const minutes = Math.floor(rounded / 60)
  if (minutes >= 60) return Math.floor(minutes / 60) + ' ч ' + (minutes % 60) + ' мин'
  if (minutes >= 10) return minutes + ' мин'
  return (minutes ? minutes + ' мин ' : '') + (rounded % 60) + ' с'
}
