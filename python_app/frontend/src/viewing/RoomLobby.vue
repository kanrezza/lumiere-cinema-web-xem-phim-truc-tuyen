<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type JoinStatus = 'pending' | 'approved' | 'rejected' | 'open'
const { endpoint, initialStatus, initialRequiresApproval, action, csrf, passwordProtected, checkUrl } = defineProps<{
  endpoint: string
  initialStatus: JoinStatus
  initialRequiresApproval: boolean
  action: string
  csrf: string
  passwordProtected: boolean
  checkUrl: string
}>()
const status = ref<JoinStatus>(initialStatus)
const requiresApproval = ref(initialRequiresApproval)
const closed = ref(false)
const awaitingApproval = computed(() => status.value === 'pending' && requiresApproval.value)
const listeners = new AbortController()
let activeRequest: AbortController | undefined
let timer: number | undefined

function stop() {
  window.clearTimeout(timer)
  activeRequest?.abort()
  activeRequest = undefined
}

async function check() {
  if (!awaitingApproval.value || closed.value) return
  const request = new AbortController()
  activeRequest = request
  try {
    const response = await fetch(endpoint, { cache: 'no-store', credentials: 'same-origin', signal: request.signal })
    if (request.signal.aborted) return
    if ([403, 404].includes(response.status) || response.redirected) {
      closed.value = true
      return
    }
    if (!response.ok) return
    const next: { status: string; requires_approval: boolean } = await response.json()
    if (request.signal.aborted) return
    if (next.status === 'approved' || next.status === 'rejected') status.value = next.status
    else if (next.status !== 'pending' || !next.requires_approval) window.location.reload()
  } catch {
    // A temporary connection problem does not invalidate the join request.
  } finally {
    if (!request.signal.aborted && awaitingApproval.value && !closed.value) timer = window.setTimeout(check, 2500)
  }
}

onMounted(() => {
  const { signal } = listeners
  window.addEventListener('pagehide', stop, { signal })
  window.addEventListener('pageshow', event => {
    if (event.persisted && awaitingApproval.value) void check()
  }, { signal })
  if (awaitingApproval.value) void check()
})
onUnmounted(() => { listeners.abort(); stop() })
</script>

<template>
  <section v-if="awaitingApproval" data-lobby-pending>
    <h2>Đang chờ chủ phòng duyệt</h2>
    <p role="status">{{ closed ? 'Phòng đã đóng hoặc bạn không còn quyền truy cập.' : 'Trang sẽ báo khi chủ phòng phản hồi.' }}</p>
    <a class="btn secondary small" :href="checkUrl">Kiểm tra lại</a>
  </section>
  <section v-else-if="status === 'rejected'" data-lobby-rejected>
    <h2>Yêu cầu đã bị từ chối</h2>
    <p>Chủ phòng đã từ chối yêu cầu vào phòng của bạn.</p>
  </section>
  <form v-else method="post" :action="action" class="room-access-form" data-lobby-form>
    <input type="hidden" name="csrfmiddlewaretoken" :value="csrf">
    <p v-if="status === 'approved'" data-lobby-approved role="status">Chủ phòng đã duyệt. Bạn có thể vào phòng.</p>
    <label v-if="passwordProtected && status !== 'approved'" data-lobby-password>
      Mật khẩu phòng<input name="password" type="password" maxlength="128" autocomplete="off" required>
    </label>
    <button class="btn" data-lobby-submit>{{ requiresApproval && status !== 'approved' ? 'Gửi yêu cầu vào phòng' : 'Tham gia phòng' }}</button>
  </form>
</template>
