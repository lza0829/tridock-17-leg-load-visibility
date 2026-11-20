<template>
  <div>
    <div class="hero"><div><h1>实收</h1><p>到货日实际点收行。结案后不可再写。</p></div><button @click="load">刷新</button></div>
    <div class="panel">
      <div class="row">
        <input v-model="form.receive_no" placeholder="实收号" />
        <input v-model="form.supplier_code" placeholder="供应商编码" />
        <input v-model="form.sku" placeholder="货号" />
        <input v-model="form.dock_day" placeholder="到货日" />
        <input v-model.number="form.qty" type="number" placeholder="数量" />
        <button @click="add" :disabled="isHeld(form.supplier_code)">登记实收</button>
      </div>
      <p class="msg" v-if="isHeld(form.supplier_code)">该供应商处于暂扣状态，实收装载将被后端拒绝。请先在「供应商暂扣」解除。</p>
      <p class="msg" v-else>{{ err }}</p>
      <p class="okmsg">{{ ok }}</p>
      <table>
        <thead><tr><th>实收号</th><th>供应商</th><th>货号</th><th>到货日</th><th>数量</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.receive_no }}</td>
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
const form = ref({ receive_no: '', supplier_code: 'SUP-A', sku: '', dock_day: '2026-11-18', qty: 1 })
async function load() { rows.value = await api('/receives') }
async function add() {
  err.value = ''; ok.value = ''
  try {
    await api('/receives', { method: 'POST', body: JSON.stringify(form.value) })
    ok.value = '已登记'
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
