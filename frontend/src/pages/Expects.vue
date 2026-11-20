<template>
  <div>
    <div class="hero"><div><h1>预报</h1><p>供应商到货预报清单（本地夹具）。</p></div><button @click="load">刷新</button></div>
    <div class="panel">
      <div class="row">
        <input v-model="form.doc_no" placeholder="单号" />
        <input v-model="form.supplier_code" placeholder="供应商编码" />
        <input v-model="form.sku" placeholder="货号" />
        <input v-model="form.dock_day" placeholder="到货日" />
        <input v-model.number="form.qty" type="number" placeholder="数量" />
        <button @click="add" :disabled="isHeld(form.supplier_code)">登记预报</button>
      </div>
      <p class="msg" v-if="isHeld(form.supplier_code)">该供应商处于暂扣状态，预报装载将被后端拒绝。请先在「供应商暂扣」解除。</p>
      <p class="msg" v-else>{{ err }}</p>
      <p class="okmsg">{{ ok }}</p>
      <table>
        <thead><tr><th>单号</th><th>供应商</th><th>货号</th><th>到货日</th><th>数量</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.doc_no }}</td>
            <td>{{ r.supplier_code }} <span v-if="isHeld(r.supplier_code)" class="tag bad">暂扣</span></td>
            <td>{{ r.sku }}</td><td>{{ r.dock_day }}</td><td>{{ r.qty }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { useHolds } from '../useHolds'
const { isHeld } = useHolds()
const rows = ref([])
const err = ref('')
const ok = ref('')
const form = ref({ doc_no: '', supplier_code: 'SUP-A', sku: '', dock_day: '2026-11-18', qty: 1 })
async function load() {
  err.value = ''
  rows.value = await api('/expects')
}
async function add() {
  err.value = ''; ok.value = ''
  try {
    await api('/expects', { method: 'POST', body: JSON.stringify(form.value) })
    ok.value = '已登记'
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
