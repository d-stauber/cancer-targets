import { useState } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
// @ts-ignore
import Plotly from 'plotly.js-dist-min'
import { plotTheme, useCurrentTheme } from '../theme'
import ExportDialog from './ExportDialog'
const Base = createPlotlyComponent(Plotly)

/** Plot with theme-aware defaults: recessive grid, text tokens, no logo. The camera button opens a customise-and-export dialog. */
export default function Plot(props: any) {
  const theme = useCurrentTheme()
  const t = plotTheme()
  const [exportGd, setExportGd] = useState<any>(null)
  const ax = { gridcolor: t.grid, zerolinecolor: t.axis, linecolor: t.axis, tickfont: { color: t.text, size: 11 }, title: { font: { color: t.text, size: 12 } } }
  const layout = { paper_bgcolor: t.paper, plot_bgcolor: t.plot, font: { family: t.font, color: t.text, size: 12 }, margin: { l: 50, r: 12, t: 24, b: 48 },
    hoverlabel: { bgcolor: t.paper, bordercolor: t.axis, font: { color: t.textStrong, family: t.font } }, ...props.layout,
    xaxis: { ...ax, ...(props.layout?.xaxis || {}) }, yaxis: { ...ax, ...(props.layout?.yaxis || {}) } }
  const config = {
    displaylogo: false, responsive: true, ...(props.config || {}),
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toImage'],
    modeBarButtonsToAdd: [{ name: 'Download plot (customise first)', icon: Plotly.Icons.camera, click: (gd: any) => setExportGd(gd) }],
  }
  return <>
    <Base key={theme} {...props} layout={layout} config={config} style={{ width: '100%', ...(props.style || {}) }} useResizeHandler />
    {exportGd && <ExportDialog gd={exportGd} onClose={() => setExportGd(null)} />}
  </>
}
