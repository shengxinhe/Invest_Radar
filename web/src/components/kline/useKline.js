import { init, dispose } from "klinecharts";

export function useKline(elRef) {
  let chart = null;

  const initChart = () => {
    if (!elRef.value || chart) return chart;
    chart = init(elRef.value, {
      locale: "zh-CN",
      timezone: "Asia/Shanghai",
      styles: {
        grid: {
          show: true,
          horizontal: { color: "rgba(255,255,255,.04)" },
          vertical: { color: "rgba(255,255,255,.04)" },
        },
        candle: {
          bar: {
            upColor: "#3DDC97", downColor: "#FF5C7A",
            upBorderColor: "#3DDC97", downBorderColor: "#FF5C7A",
            upWickColor: "#3DDC97", downWickColor: "#FF5C7A",
          },
          priceMark: { last: { show: true } },
        },
        crosshair: {
          horizontal: {
            line: { color: "#5EEAD4", style: "dashed" },
            text: { backgroundColor: "#0F1220", borderColor: "#5EEAD4" },
          },
          vertical: {
            line: { color: "#5EEAD4", style: "dashed" },
            text: { backgroundColor: "#0F1220", borderColor: "#5EEAD4" },
          },
        },
        indicator: {
          bars: [
            { upColor: "rgba(61,220,151,.5)", downColor: "rgba(255,92,122,.5)",
              noChangeColor: "rgba(138,143,163,.4)" },
          ],
        },
      },
    });
    return chart;
  };

  const bindCrosshair = (onBar) => {
    if (!chart) return;
    chart.subscribeAction("onCrosshairChange", (data) => {
      if (!data || !data.kLineData) return onBar(null);
      onBar(data.kLineData);
    });
  };

  const load = (bars) => {
    if (!chart) return;
    chart.applyNewData(
      bars.map((b) => ({
        timestamp: b.timestamp, open: b.open, high: b.high,
        low: b.low, close: b.close, volume: b.volume, turnover: b.turnover,
      }))
    );
  };

  const loadTimeline = (points, preClose) => {
    if (!chart) return;
    // 分时：用 close=price 喂给图表（蜡烛退化为线）
    chart.applyNewData(
      points.map((p) => ({
        timestamp: p.timestamp, open: p.price, high: p.price,
        low: p.price, close: p.price, volume: p.volume,
      }))
    );
    // 昨收基准虚线
    if (preClose) {
      chart.createOverlay({
        name: "horizontalStraightLine",
        mode: "normal",
        points: [{ value: preClose }],
        styles: {
          line: { color: "#8A8FA3", style: "dashed", dashValue: [4, 4] },
        },
      });
    }
  };

  const createMA = () => {
    if (!chart) return;
    chart.createIndicator("MA", false, { id: "candle_pane" });
    chart.createIndicator("VOL", false, { id: "vol_pane" });
  };

  const setPeriod = () => {
    if (!chart) return;
    // 切周期时清掉 overlays（昨收线等）
    chart.removeOverlay();
  };

  return {
    initChart, bindCrosshair, load, loadTimeline, createMA, setPeriod,
    getChart: () => chart,
    disposeChart: () => {
      if (chart && elRef.value) {
        dispose(elRef.value);
        chart = null;
      }
    },
  };
}
