<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  plans: { id: string; name: string; duration: string; price: string; start?: string; end?: string }[]
  selected: string
  renewing?: boolean
}>()
const selectedPlan = ref(props.selected)
const total = computed(() => props.plans.find(plan => plan.id === selectedPlan.value)?.price || '')
const period = computed(() => props.plans.find(plan => plan.id === selectedPlan.value))
function dateLabel(value?: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return ''
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date(value))
}
</script>

<template>
  <fieldset class="membership-options">
    <legend class="sr-only">Thời hạn gói VIP</legend>
    <label v-for="plan in plans" :key="plan.id" class="membership-option plan-option">
      <input v-model="selectedPlan" name="plan" type="radio" :value="plan.id" :data-price="plan.price" required>
      <span class="membership-option-name"><strong>{{ plan.name }}</strong><small>{{ plan.duration }}</small></span>
      <span class="membership-price">{{ plan.price }} <small>₫</small></span>
    </label>
  </fieldset>
  <div class="membership-purchase-note">
    <svg class="icon" aria-hidden="true"><use href="#i-check" /></svg>Các gói có cùng quyền lợi VIP
  </div>
  <section v-if="period?.start && period?.end" class="membership-renewal-preview" aria-label="Kỳ sử dụng dự kiến" aria-live="polite" aria-atomic="true">
    <strong>{{ renewing ? 'Gói mới tiếp nối thời gian VIP hiện tại' : 'Kỳ sử dụng dự kiến' }}</strong>
    <dl><div><dt>Bắt đầu</dt><dd>{{ dateLabel(period.start) }}</dd></div><div><dt>Kết thúc</dt><dd>{{ dateLabel(period.end) }}</dd></div></dl>
    <p>Thời gian chính xác được ghi nhận sau khi thanh toán thành công. Thời gian VIP còn lại được giữ nguyên.</p>
  </section>
  <div class="membership-total">
    <span>Thanh toán một lần</span>
    <strong aria-live="polite" aria-atomic="true"><span id="selected-price">{{ total }}</span> ₫</strong>
  </div>
</template>
