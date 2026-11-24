import { expect, test } from 'vitest'
import type { Settings } from './api'
import { validateSettings } from './settingsValidation'

function settings(): Settings {
  return {
    name: 'Север',
    timezone: 'Asia/Krasnoyarsk',
    observation_minutes: 30,
    processing_delay_minutes: 60,
    weekly_hours: Array.from({ length: 7 }, () => ({ mode: 'closed', intervals: [] })),
    overrides: [],
  }
}

test('allows an adjacent night shift and rejects an overlapping date override', () => {
  const value = settings()
  value.weekly_hours[4] = { mode: 'intervals', intervals: [{ opens: '12:00', closes: '02:00' }] }
  value.weekly_hours[5] = { mode: 'intervals', intervals: [{ opens: '02:00', closes: '22:00' }] }
  expect(validateSettings(value)).toEqual([])
  value.overrides = [{ day: '2026-01-10', hours: { mode: 'all_day', intervals: [] } }]
  expect(validateSettings(value)).toEqual(['Рабочие интервалы пересекаются рядом с исключением 2026-01-10.'])
})

test('requires distinct opening and closing times in interval mode', () => {
  const value = settings()
  value.weekly_hours[4] = { mode: 'intervals', intervals: [{ opens: '12:00', closes: '12:00' }] }
  expect(validateSettings(value)).toEqual(['Время открытия и закрытия совпадает. Выберите «Круглосуточно».'])
})
