<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/github.css'
const props = defineProps<{ text: string }>()
const md = new MarkdownIt({ html: false, linkify: true, breaks: true,
  highlight(code, language) { return language && hljs.getLanguage(language) ? hljs.highlight(code, { language }).value : '' },
})
const html = computed(() => DOMPurify.sanitize(md.render(props.text), { FORBID_TAGS: ['img'] }))
</script>
<template><div class="markdown" v-html="html" /></template>
