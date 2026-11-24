/**
 * M3 · useSearch —— 带竞态保护的搜索
 * 防抖 + AbortController + 请求序号，旧响应永不覆盖新结果
 */
import { ref, onUnmounted } from "vue";

export function useSearch(fetcher, { delay = 220 } = {}) {
  const q = ref("");
  const results = ref([]);
  const searching = ref(false);
  const error = ref("");

  let timer = null;
  let seq = 0;
  let ctrl = null;

  function cancel() {
    if (ctrl) {
      ctrl.abort();
      ctrl = null;
    }
    clearTimeout(timer);
  }

  function onInput() {
    const kw = q.value.trim();
    cancel();
    if (!kw) {
      results.value = [];
      searching.value = false;
      error.value = "";
      return;
    }
    searching.value = true;
    const mySeq = ++seq;
    timer = setTimeout(async () => {
      ctrl = new AbortController();
      try {
        const r = await fetcher(kw, ctrl.signal);
        if (mySeq !== seq) return;        // 过期响应丢弃
        results.value = r || [];
        error.value = "";
      } catch (e) {
        if (mySeq !== seq) return;
        if (e?.name === "AbortError") return;
        error.value = e?.message || "搜索失败";
        results.value = [];
      } finally {
        if (mySeq === seq) searching.value = false;
      }
    }, delay);
  }

  function reset() {
    cancel();
    q.value = "";
    results.value = [];
    searching.value = false;
    error.value = "";
    seq++;
  }

  onUnmounted(cancel);

  return { q, results, searching, error, onInput, reset };
}
