<template>
  <div>
    <div class="hero">
      <div>
        <h1>供应商暂扣</h1>
        <p>回执稽核未过可暂扣供应商。架构 A：暂扣生效后该供应商的预报/实收/回执装载一律由后端拒绝，对齐剔除其键、批次快照暂扣数，含其键的批次无法封印。前端禁用仅为提示，真正闸口在后端。</p>
      </div>
      <button @click="load">刷新</button>
    </div>

    <div class="panel">
      <h2>设置 / 解除暂扣</h2>
      <div class="row">
        <input v-model="form.supplier_code" placeholder="供应商编码（如 SUP-A）" />
        <input v-model="form.reason" placeholder="暂扣原因（必填）" />
        <button @click="place">暂扣该供应商</button>
      </div>
      <p class="msg">{{ err }}</p>
      <p class="okmsg">{{ ok }}</p>
    </div>

    <div class="panel">
      <h2>活动暂扣（{{ active.length }}）</h2>
      <table>
        <thead><tr><th>供应商</th><th>原因</th><th>暂扣时间</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="h in active" :key="h.supplier_code">
            <td>{{ h.supplier_code }}</td>
            <td>{{ h.reason }}</td>
            <td>{{ h.created_at }}</td>
            <td><span class="tag bad">暂扣中</span></td>
            <td><button class="secondary" @click="release(h.supplier_code)">解除暂扣</button></td>
          </tr>
          <tr v-if="!active.length"><td colspan="5">暂无活动暂扣</td></tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h2>审计流</h2>
      <table>
        <thead><tr><th>时间</th><th>供应商</th><th>动作</th><th>原因/说明</th><th>操作人</th></tr></thead>
        <tbody>
          <tr v-for="a in audit" :key="a.id">
            <td>{{ a.created_at }}</td>
            <td>{{ a.supplier_code }}</td>
            <td><span class="tag" :class="actionClass(a.action)">{{ actionLabel(a.action) }}</span></td>
            <td>{{ a.reason }}</td>
            <td>{{ a.actor }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
const holds = ref([])
const audit = ref([])
const err = ref('')
const ok = ref('')
const form = ref({ supplier_code: '', reason: '' })
const active = computed(() => holds.value.filter(h => h.released_at == null))

async function load() {
  err.value = ''
  try {
    holds.value = await api('/holds')
    audit.value = await api('/holds/audit')
  } catch (e) { err.value = e.message }
}
async function place() {
  err.value = ''; ok.value = ''
  if (!form.value.supplier_code.trim() || !form.value.reason.trim()) {
    err.value = '供应商编码与暂扣原因均必填'
    return
  }
  try {
    await api('/holds', { method: 'POST', body: JSON.stringify(form.value) })
    ok.value = `已暂扣 ${form.value.supplier_code}`
    form.value = { supplier_code: '', reason: '' }
    await load()
  } catch (e) { err.value = e.message }
}
async function release(code) {
  err.value = ''; ok.value = ''
  try {
    await api(`/holds/${code}/release`, { method: 'POST', body: JSON.stringify({}) })
    ok.value = `已解除 ${code} 暂扣`
    await load()
  } catch (e) { err.value = e.message }
}
function actionLabel(a) {
  return { place: '暂扣', release: '解除', seal: '封印' }[a] || a
}
function actionClass(a) {
  return a === 'place' ? 'bad' : a === 'release' ? 'ok' : 'seal'
}
onMounted(load)
</script>
