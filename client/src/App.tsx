import { useEffect, useMemo, useState, ReactNode } from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, BarChart, Bar } from 'recharts'
import { motion } from 'framer-motion'
import { Coffee, Flame, Calendar, Package, Leaf } from 'lucide-react'

interface Produto { id:number; nome:string; categoria:string; quantidade:number; preco:number; unidade:string }

export default function App(){
  const [produtos, setProdutos] = useState<Produto[]>([])
  const [vendas, setVendas] = useState<any>(null)
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<keyof Produto>('nome')
  const [sortDir, setSortDir] = useState<'asc'|'desc'>('asc')

  useEffect(()=>{
    fetch('/api/produtos').then(r=>r.json()).then(j=> setProdutos(j.items||[]))
    fetch('/api/vendas').then(r=>r.json()).then(setVendas)
  },[])

  const filtered = useMemo(()=>{
    const q = query.toLowerCase()
    const base = produtos.filter(p => p.nome.toLowerCase().includes(q) || (p.categoria||'').toLowerCase().includes(q))
    return base.sort((a,b)=>{
      const av = a[sortKey]; const bv = b[sortKey]
      if(av<bv) return sortDir==='asc'?-1:1
      if(av>bv) return sortDir==='asc'?1:-1
      return 0
    })
  },[produtos, query, sortKey, sortDir])

  const monthlyData = useMemo(()=>{
    const labels:string[] = vendas?.mensal?.labels || []
    const vals:number[] = vendas?.mensal?.values || []
    return labels.map((l:string, i:number)=> ({ name:l.slice(2), total: Number(vals[i]||0) }))
  },[vendas])

  const topCatData = useMemo(()=>{
    const labels:string[] = vendas?.por_categoria?.labels || []
    const vals:number[] = vendas?.por_categoria?.values || []
    return labels.map((l:string, i:number)=> ({ name:l, total: Number(vals[i]||0) }))
  },[vendas])

  function toggleSort(key: keyof Produto){
    if(sortKey===key){ setSortDir(sortDir==='asc'?'desc':'asc') }
    else { setSortKey(key); setSortDir('asc') }
  }

  return (
    <div className="min-h-screen bg-coffee-50 text-coffee-900">
      <header className="sticky top-0 z-10 backdrop-blur bg-white/70 border-b border-coffee-100">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gold to-coffee-600 flex items-center justify-center text-coffee-900">
            <Coffee className="w-4 h-4" />
          </div>
          <h1 className="font-display font-bold text-xl">Eos Cafés Especiais</h1>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-4">
        {/* Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card title="Vendas Hoje" value={fmtCurrency(vendas?.totals?.day)} icon={<Flame className="w-5 h-5" />} />
          <Card title="Vendas Mês" value={fmtCurrency(vendas?.totals?.month)} icon={<Calendar className="w-5 h-5" />} />
          <Card title="Produtos" value={produtos.length.toString()} icon={<Package className="w-5 h-5" />} />
          <Card title="Categorias" value={String(new Set(produtos.map(p=>p.categoria)).size)} icon={<Leaf className="w-5 h-5" />} />
        </div>

        {/* Gráficos */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
          <Panel title="Evolução Mensal" subtitle="Últimos 12 meses">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={monthlyData}>
                  <XAxis dataKey="name" stroke="#6b5f56" />
                  <YAxis stroke="#6b5f56" />
                  <Tooltip formatter={(v)=> fmtCurrency(Number(v))} />
                  <Line type="monotone" dataKey="total" stroke="#c9a86a" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>
          <Panel title="Vendas por Categoria" subtitle="Últimos 30 dias">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topCatData}>
                  <XAxis dataKey="name" stroke="#6b5f56" />
                  <YAxis stroke="#6b5f56" />
                  <Tooltip formatter={(v)=> fmtCurrency(Number(v))} />
                  <Bar dataKey="total" fill="#8a633f" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>
        </div>

        {/* Tabela estilo APITable */}
        <Panel title="Inventário" subtitle="Edição rápida, filtro e ordenação">
          <div className="flex items-center justify-between gap-2 mb-3">
            <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Buscar..." className="px-3 py-2 border rounded-md border-coffee-200 w-full max-w-xs focus:outline-none focus:ring-2 focus:ring-gold" />
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left border-b border-coffee-200">
                  <Th onClick={()=>toggleSort('nome')} label="Produto" active={sortKey==='nome'} dir={sortDir} />
                  <Th onClick={()=>toggleSort('categoria')} label="Categoria" active={sortKey==='categoria'} dir={sortDir} />
                  <Th onClick={()=>toggleSort('quantidade')} label="Qtd" active={sortKey==='quantidade'} dir={sortDir} />
                  <Th onClick={()=>toggleSort('preco')} label="Preço" active={sortKey==='preco'} dir={sortDir} />
                  <th className="py-2 px-3">Total</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(p=> (
                  <tr key={p.id} className="border-b border-coffee-100 hover:bg-white">
                    <td className="py-2 px-3 font-medium">{p.nome}</td>
                    <td className="py-2 px-3">{p.categoria}</td>
                    <td className="py-2 px-3">
                      <InlineNumber value={p.quantidade} /> {p.unidade}
                    </td>
                    <td className="py-2 px-3">{fmtCurrency(p.preco)}</td>
                    <td className="py-2 px-3">{fmtCurrency(p.preco * p.quantidade)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </main>
    </div>
  )
}

function Card({ title, value, icon }:{ title:string; value:string; icon:ReactNode }){
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }} className="rounded-xl border border-coffee-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-gold/40 to-coffee-500/20 flex items-center justify-center text-coffee-900">{icon}</div>
        <div>
          <div className="text-coffee-700 text-sm">{title}</div>
          <div className="text-lg font-bold">{value||'—'}</div>
        </div>
      </div>
    </motion.div>
  )
}

function Panel({ title, subtitle, children }:{ title:string; subtitle?:string; children:any }){
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: .3 }} className="rounded-xl border border-coffee-200 bg-white p-4 shadow-sm">
      <div className="mb-3">
        <h2 className="font-semibold text-coffee-900">{title}</h2>
        {subtitle && <p className="text-sm text-coffee-600">{subtitle}</p>}
      </div>
      {children}
    </motion.section>
  )
}

function Th({ label, onClick, active, dir }:{ label:string; onClick:()=>void; active:boolean; dir:'asc'|'desc'}){
  return (
    <th className="py-2 px-3 select-none cursor-pointer" onClick={onClick}>
      <span className={active? 'text-coffee-900 font-semibold' : ''}>{label}</span>
      {active && <span className="ml-2 text-xs">{dir==='asc'? '▲':'▼'}</span>}
    </th>
  )
}

function InlineNumber({ value }:{ value:number }){
  const [val, setVal] = useState<number>(value)
  return (
    <input type="number" className="w-24 px-2 py-1 border rounded-md border-coffee-200" value={val} onChange={e=>setVal(Number(e.target.value))} />
  )
}

function fmtCurrency(n?: number){
  const v = Number(n||0)
  return 'R$ ' + v.toFixed(2).replace('.', ',')
}
