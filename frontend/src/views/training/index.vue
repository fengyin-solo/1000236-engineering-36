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

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="selectedIds.length" class="batch-bar">
      <span>已选 {{ selectedIds.length }} 条</span>
      <button class="btn primary" type="button" :disabled="batchRunning" @click="runBatch('确认完成')">
        批量确认完成
      </button>
      <button class="btn" type="button" :disabled="batchRunning" @click="runBatch('退回补考')">
        批量退回补考
      </button>
      <button class="btn ghost" type="button" :disabled="batchRunning" @click="clearSelection">清空选择</button>
    </div>

    <div v-if="batchResults.length" class="batch-panel">
      <p class="batch-title">{{ batchMessage }}</p>
      <ul class="batch-list">
        <li
          v-for="(item, index) in batchResults"
          :key="index"
          :class="item.ok ? 'batch-ok' : 'batch-skip'"
        >
          {{ item.message }}
        </li>
      </ul>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">
            <input type="checkbox" :checked="allChecked" :disabled="!rows.length" @change="toggleAll" />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input v-model="selectedIds" type="checkbox" :value="Number(row.id)" />
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

    <footer class="page-foot">
      <span>共 {{ total }} 条安全培训记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BatchItem = { id: number; ok: boolean; message: string }

const ENDPOINT = '/api/training'
const columns = ["培训编号", "培训主题", "培训讲师", "培训日期", "参训人数", "考核通过", "培训资料", "培训状态"]
const actions = ["组织培训", "登记考核", "安排补训"]
const batchActions = ["确认完成", "退回补考"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const summary = ref<Record<string, number>>({ 记录总数: 0, 参训人数: 0, 完成数量: 0, 需补训数量: 0 })
const stats = computed(() => [
  { label: '参训人数', value: summary.value['参训人数'] ?? 0 },
  { label: '完成数量', value: summary.value['完成数量'] ?? 0 },
  { label: '待补训数量', value: summary.value['需补训数量'] ?? 0 },
])

const selectedIds = ref<number[]>([])
const batchRunning = ref(false)
const batchMessage = ref('')
const batchResults = ref<BatchItem[]>([])

const allChecked = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selectedIds.value.includes(Number(row.id))),
)

function toggleAll() {
  selectedIds.value = allChecked.value ? [] : rows.value.map((row) => Number(row.id))
}

function clearSelection() {
  selectedIds.value = []
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
      body: JSON.stringify({ action }),
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
  errorMessage.value = ''
  batchMessage.value = ''
  batchResults.value = []
  if (!batchActions.includes(action)) {
    errorMessage.value = `动作「${action}」不支持批量执行`
    return
  }
  if (!selectedIds.value.length) {
    errorMessage.value = '请先勾选要批量处理的培训记录'
    return
  }
  batchRunning.value = true
  try {
    const response = await request(`${ENDPOINT}/batch-actions`, {
      method: 'POST',
      body: JSON.stringify({ ids: selectedIds.value, action }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || '批量处理未生效，请稍后重试')
    }
    batchMessage.value = payload.message ?? ''
    batchResults.value = payload.results ?? []
    if (payload.summary) {
      summary.value = payload.summary
    }
    selectedIds.value = []
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量处理失败'
  } finally {
    batchRunning.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok) {
      throw new Error('培训记录列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      summary.value = await summaryResponse.json()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训列表读取失败'
  }
}

onMounted(reload)
</script>
