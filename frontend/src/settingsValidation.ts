import type { DayHours, Settings } from './api'
import { shiftDay } from './format'

const clock = /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/
const weekday = (day: string) => (new Date(day + 'T00:00:00Z').getUTCDay() + 6) % 7
const minutes = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3))
const dayMinutes = 1440
type Slot = [number, number]

function slots(hours: DayHours, day: number): Slot[] {
  const base = day * dayMinutes
  if (hours.mode === 'closed') return []
  if (hours.mode === 'all_day') return [[base, base + dayMinutes]]
  return hours.intervals.map(interval => {
    const opens = minutes(interval.opens)
    const closes = minutes(interval.closes)
    return [base + opens, base + closes + (closes < opens ? dayMinutes : 0)]
  })
}

function overlaps(intervals: Slot[]) {
  intervals.sort(([a], [b]) => a - b)
  return intervals.some(([start], index) => index > 0 && start < intervals[index - 1][1])
}

export function validateSettings(settings: Settings) {
  const errors: string[] = []
  if (!settings.name.trim() || settings.name.trim().length > 120) errors.push('Укажите название ресторана, до 120 символов.')
  try {
    new Intl.DateTimeFormat('ru', { timeZone: settings.timezone })
  } catch {
    errors.push('Укажите часовой пояс IANA, например Asia/Krasnoyarsk.')
  }
  for (const [value, label] of [
    [settings.observation_minutes, 'Запас наблюдения'],
    [settings.processing_delay_minutes, 'Задержка обработки'],
  ] as const) {
    if (!Number.isInteger(value) || value < 0 || value > 1440) errors.push(label + ' должен быть указан целым числом от 0 до 1440 минут.')
  }
  for (const hours of [...settings.weekly_hours, ...settings.overrides.map(item => item.hours)]) {
    if (hours.mode !== 'intervals') continue
    if (!hours.intervals.length) errors.push('Добавьте рабочий интервал или измените режим дня.')
    if (hours.intervals.some(item => !clock.test(item.opens) || !clock.test(item.closes))) errors.push('Заполните время открытия и закрытия.')
    if (hours.intervals.some(item => item.opens === item.closes && clock.test(item.opens))) errors.push('Время открытия и закрытия совпадает. Выберите «Круглосуточно».')
  }
  const overrides = new Map(settings.overrides.map(item => [item.day, item.hours]))
  if (settings.overrides.length !== overrides.size) errors.push('Для одной даты допускается одно исключение.')
  const validOverrides = [...overrides.keys()].filter(day => /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(Date.parse(day)) && Number(day.slice(0, 4)) >= 2 && Number(day.slice(0, 4)) <= 9998)
  if (validOverrides.length !== overrides.size) errors.push('Укажите корректную дату каждого исключения.')
  if (overlaps([...settings.weekly_hours, settings.weekly_hours[0]].flatMap((hours, index) => slots(hours, index)))) {
    errors.push('Рабочие интервалы недельного графика пересекаются.')
  }
  for (const day of validOverrides) {
    const local = [-1, 0, 1].flatMap(offset => {
      const nearby = shiftDay(day, offset)
      return slots(overrides.get(nearby) ?? settings.weekly_hours[weekday(nearby)], offset)
    })
    if (overlaps(local)) errors.push('Рабочие интервалы пересекаются рядом с исключением ' + day + '.')
  }
  return [...new Set(errors)]
}
