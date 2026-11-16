<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  inputName: string
  initialQuery: string
  placeholder: string
  label: string
  hiddenFields: { name: string; value: string }[]
  help: string
  resultCount: string
  clearHref: string
  clearLabel: string
}>()

const query = ref(props.initialQuery)
const input = ref<HTMLInputElement>()

function clearQuery() {
  query.value = ''
  input.value?.focus()
}
</script>

<template>
  <form id="changelist-search" method="get" role="search">
    <div>
      <label for="searchbar">
        <svg class="studio-icon" aria-hidden="true"><use href="#s-search" /></svg>
        <span class="visually-hidden">{{ label }}</span>
      </label>
      <input v-model="query" ref="input" id="searchbar" type="search" :name="inputName"
             :placeholder="placeholder" :aria-describedby="help ? 'searchbar_helptext' : undefined">
      <input type="submit" value="Tìm kiếm">
      <button v-if="query" class="studio-clear-search" type="button" @click="clearQuery">
        Xóa từ khóa
      </button>
      <span v-if="clearHref" class="small quiet">
        {{ resultCount }} <a :href="clearHref">{{ clearLabel }}</a>
      </span>
      <input v-for="(field, index) in hiddenFields" :key="index"
             type="hidden" :name="field.name" :value="field.value">
    </div>
    <div v-if="help" class="help" id="searchbar_helptext">{{ help }}</div>
  </form>
</template>
