<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  plans: { id: string; name: string; duration: string; price: string }[]
  selected: string
}>()
const selectedPlan = ref(props.selected)
const total = computed(() => props.plans.find(plan => plan.id === selectedPlan.value)?.price || '')
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
  <div class="membership-total">
    <span>Thanh toán một lần</span>
    <strong aria-live="polite" aria-atomic="true"><span id="selected-price">{{ total }}</span> ₫</strong>
  </div>
</template>
