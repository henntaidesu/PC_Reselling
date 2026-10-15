<template>
  <!-- 筛选下拉里的一个选项：左边名称，右边「选它之后会筛出几件」。
       件数靠右、等宽数字，一列看下来才比得出哪个多；为 0 的（已选、但在当前其余条件下
       已经没有货了）压暗，提示这一项现在筛不出东西。 -->
  <span class="facet-label">
    <span class="facet-name">{{ label }}</span>
    <span class="facet-count" :class="{ 'is-zero': !count }">{{ count }}</span>
  </span>
</template>

<script setup>
defineProps({
  label: { type: String, default: '' },
  count: { type: Number, default: 0 }
})
</script>

<style scoped>
.facet-label { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.facet-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.facet-count { flex: none; color: var(--pcr-text-dim); font-size: 12px; font-variant-numeric: tabular-nums; }
.facet-count.is-zero { opacity: 0.5; }
</style>
