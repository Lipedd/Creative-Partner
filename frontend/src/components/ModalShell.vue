<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { X } from 'lucide-vue-next'
defineProps<{ title: string; subtitle?: string; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
const previouslyFocused = document.activeElement as HTMLElement | null
onMounted(() => dialog.value?.showModal())
onUnmounted(() => previouslyFocused?.focus())
</script>
<template>
  <Teleport to="body"><dialog ref="dialog" class="modal" :class="{ wide }" @cancel.prevent="emit('close')" @click="e => { if(e.target === dialog) emit('close') }">
    <header class="modal-heading"><div><h2>{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p></div><button class="icon-button" aria-label="关闭对话框" @click="emit('close')"><X :size="20" /></button></header>
    <div class="modal-content"><slot /></div>
  </dialog></Teleport>
</template>
