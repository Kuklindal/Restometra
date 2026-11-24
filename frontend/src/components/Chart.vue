<script setup lang="ts">
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { init, use, type EChartsCoreOption, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

use([BarChart, LineChart, TooltipComponent, GridComponent, CanvasRenderer])
const props = defineProps<{ options: EChartsCoreOption; label: string }>()
const container = ref<HTMLDivElement>()
let chart: EChartsType | undefined
let observer: ResizeObserver | undefined

onMounted(() => {
  if (!container.value) return
  chart = init(container.value)
  chart.setOption(props.options)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(container.value)
})
watch(() => props.options, options => chart?.setOption(options, true))
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="container" class="chart" role="img" :aria-label="label"></div>
</template>
