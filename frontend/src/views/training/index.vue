<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>安全培训管理</h2>
        <p class="page-desc">维护培训记录，围绕培训编号、培训主题、培训讲师、培训日期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记培训记录</button>
        <button class="btn" type="button" @click="exportRows">导出安全培训清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload()">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="batch-bar">
      <label class="select-all">
        <input type="checkbox" :checked="allSelected" :indeterminate.prop="someSelected" @change="toggleAll" />
        全选当前页
      </label>
      <span class="batch-tip">已选 {{ selectedIds.size }} 条</span>
      <button
        v-for="action in batchActions"
        :key="action"
        class="btn"
        type="button"
        :disabled="!selectedIds.size || batchLoading"
        @click="runBatch(action)"
      >
        批量{{ action }}
      </button>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">选择</th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input
              type="checkbox"
              :checked="selectedIds.has(Number(row.id))"
              @change="toggleOne(Number(row.id))"
            />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无安全培训数据，可先登记培训记录</td>
        </tr>
      </tbody>
    </table>

    <section v-if="batchResult" class="batch-result">
      <header class="batch-result-head">
        <strong>{{ batchResult.message }}</strong>
        <button class="link" type="button" @click="batchResult = null">关闭</button>
      </header>
      <ul class="batch-result-list">
        <li
          v-for="item in batchResult.results"
          :key="`${item.entry_id}-${item.code}`"
          :class="item.ok ? 'result-ok' : 'result-skip'"
        >
          <span class="result-mark">{{ item.ok ? '✓' : '!' }}</span>
          <span>记录 {{ item.entry_id }}：{{ item.message }}</span>
        </li>
      </ul>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条安全培训记录</span>
      <span v-if="batchLoading" class="pending-text">批量处理中…</span>
      <span v-else-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

type BatchItemResult = {
  entry_id: number
  ok: boolean
  code: string
  message: string
}

type BatchResult = {
  ok: boolean
  action: string
  message: string
  results: BatchItemResult[]
  success_count: number
  skipped_count: number
  statistics: Record<string, number>
}

const ENDPOINT = '/api/training'
const columns = ["培训编号", "培训主题", "培训讲师", "培训日期", "参训人数", "考核通过", "培训资料", "培训状态"]
const actions = ["组织培训", "登记考核", "安排补训"]
const batchActions = ["确认完成", "退回补考"]
const statLabels = ["参训人数", "完成数量", "待补训数量"]
const stats = ref(statLabels.map((label) => ({ label, value: 0 })))

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const selectedIds = ref<Set<number>>(new Set())
const batchLoading = ref(false)
const batchResult = ref<BatchResult | null>(null)

const allSelected = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selectedIds.value.has(Number(row.id))),
)
const someSelected = computed(
  () => !allSelected.value && rows.value.some((row) => selectedIds.value.has(Number(row.id))),
)

function toggleOne(id: number) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  selectedIds.value = next
}

function toggleAll() {
  if (allSelected.value) {
    const pageIds = new Set(rows.value.map((row) => Number(row.id)))
    selectedIds.value = new Set([...selectedIds.value].filter((id) => !pageIds.has(id)))
  } else {
    selectedIds.value = new Set([
      ...selectedIds.value,
      ...rows.value.map((row) => Number(row.id)),
    ])
  }
}

function applyStatistics(statistics: Record<string, number>) {
  stats.value = statLabels.map((label) => ({ label, value: statistics[label] ?? 0 }))
}

async function loadStatistics() {
  try {
    const response = await request(`${ENDPOINT}/statistics`)
    if (!response.ok) {
      return
    }
    applyStatistics(await response.json())
  } catch {
    // 统计卡片刷新失败不阻断列表操作
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '培训记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('安全培训动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训操作失败'
  }
}

async function runBatch(action: string) {
  if (!selectedIds.value.size || batchLoading.value) {
    return
  }
  errorMessage.value = ''
  batchLoading.value = true
  const entryIds = [...selectedIds.value]
  try {
    const response = await request(`${ENDPOINT}/batch-actions`, {
      method: 'POST',
      body: JSON.stringify({ action, entry_ids: entryIds }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail ?? '批量操作未生效，请稍后重试')
    }
    batchResult.value = payload as BatchResult
    applyStatistics(batchResult.value.statistics)
    selectedIds.value = new Set()
    await reload({ keepBatchResult: true })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量操作失败'
  } finally {
    batchLoading.value = false
  }
}

async function reload(options: { keepBatchResult?: boolean } = {}) {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('培训记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 翻页/筛选后丢弃已不在当前页的选择，避免误操作不可见记录
    const pageIds = new Set(rows.value.map((row: Row) => Number(row.id)))
    selectedIds.value = new Set([...selectedIds.value].filter((id) => pageIds.has(id)))
    await loadStatistics()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训列表读取失败'
  }
  if (!options.keepBatchResult) {
    batchResult.value = null
  }
}

onMounted(reload)
</script>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 13px;
}

.batch-bar .select-all {
  display: flex;
  align-items: center;
  gap: 6px;
}

.batch-bar .btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.batch-tip {
  color: var(--muted);
  margin-right: auto;
}

.check-col {
  width: 42px;
  text-align: center;
}

.batch-result {
  margin-top: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}

.batch-result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  margin-bottom: 8px;
}

.batch-result-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
}

.batch-result-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.result-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 12px;
  color: #fff;
  flex-shrink: 0;
}

.result-ok {
  color: #17653a;
}

.result-ok .result-mark {
  background: #16a34a;
}

.result-skip {
  color: #b42318;
}

.result-skip .result-mark {
  background: #dc2626;
}

.pending-text {
  color: var(--brand);
}
</style>
