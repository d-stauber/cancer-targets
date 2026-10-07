import { NavLink, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Explorer from './pages/Explorer'
import Gene from './pages/Gene'
import ContextPage from './pages/Context'
import Controls from './pages/Controls'
import GeneSearch from './components/GeneSearch'
import { ThemeContext, useTheme } from './theme'

export default function App() {
  const [theme, toggle] = useTheme()
  return (
    <ThemeContext.Provider value={theme}>
      <nav className="top">
        <NavLink to="/" className="brand"><i />Cancer Targets</NavLink>
        <NavLink to="/explorer" className="link">Explorer</NavLink>
        <NavLink to="/context" className="link">Target rankings</NavLink>
        <NavLink to="/controls" className="link">Custom controls</NavLink>
        <div className="spacer" />
        <GeneSearch />
        <button className="icon-btn" onClick={toggle} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} style={{ marginLeft: 8 }}>{theme === 'dark' ? '☀' : '☾'}</button>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/explorer" element={<Explorer />} />
          <Route path="/gene/:symbol" element={<Gene />} />
          <Route path="/context" element={<ContextPage />} />
          <Route path="/context/:id" element={<ContextPage />} />
          <Route path="/controls" element={<Controls />} />
        </Routes>
      </main>
    </ThemeContext.Provider>
  )
}
