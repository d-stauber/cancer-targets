import createPlotlyComponent from 'react-plotly.js/factory'
// @ts-ignore
import Plotly from 'plotly.js-dist-min'
import { plotTheme, useCurrentTheme } from '../theme'
const Base = createPlotlyComponent(Plotly)

/** Plot with theme-aware defaults: recessive grid, text tokens, no logo. */
export default function Plot(props: any) {
  const theme = useCurrentTheme()
  const t = plotTheme()
  const ax = { gridcolor: t.grid, zerolinecolor: t.axis, linecolor: t.axis, tickfont: { color: t.text, size: 11 }, title: { font: { color: t.text, size: 12 } } }
  const layout = { paper_bgcolor: t.paper, plot_bgcolor: t.plot, font: { family: t.font, color: t.text, size: 12 }, margin: { l: 50, r: 12, t: 24, b: 48 },
    hoverlabel: { bgcolor: t.paper, bordercolor: t.axis, font: { color: t.textStrong, family: t.font } }, ...props.layout,
    xaxis: { ...ax, ...(props.layout?.xaxis || {}) }, yaxis: { ...ax, ...(props.layout?.yaxis || {}) } }
  return <Base key={theme} {...props} layout={layout} config={{ displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'], ...(props.config || {}) }} style={{ width: '100%', ...(props.style || {}) }} useResizeHandler />
}
