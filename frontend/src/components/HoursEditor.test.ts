import { expect, test } from 'vitest'
import { createApp, h, nextTick, ref } from 'vue'
import type { DayHours } from '../api'
import HoursEditor from './HoursEditor.vue'

test('edits a split shift, identifies overnight hours and switches to explicit all-day mode', async () => {
  const state = ref<DayHours>({ mode: 'closed', intervals: [] })
  const root = document.createElement('div')
  const app = createApp(() => h(HoursEditor, {
    hours: state.value, label: 'Пятница',
    'onUpdate:hours': (hours: DayHours) => { state.value = hours },
  }))
  app.mount(root)
  try {
    const mode = root.querySelector('select')!
    mode.value = 'intervals'
    mode.dispatchEvent(new Event('change'))
    await nextTick()
    root.querySelector<HTMLButtonElement>('button')!.click()
    await nextTick()
    expect(state.value.intervals).toHaveLength(2)
    const closing = root.querySelectorAll('input')[1]
    closing.value = '02:00'
    closing.dispatchEvent(new Event('input'))
    await nextTick()
    expect(root.textContent).toContain('+1 день')
    mode.value = 'all_day'
    mode.dispatchEvent(new Event('change'))
    await nextTick()
    expect(state.value).toEqual({ mode: 'all_day', intervals: [] })
    expect(root.querySelector('input')).toBeNull()
  } finally {
    app.unmount()
  }
})
