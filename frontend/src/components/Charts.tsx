import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { cx } from '../lib/utils';
import { EmptyState } from './ui';

const axis = { fontSize: 11, fill: 'rgb(var(--c-muted))' };
const tooltipStyle = {
  background: 'rgb(var(--c-surface))',
  border: '1px solid rgb(var(--c-line))',
  borderRadius: 12,
  color: 'rgb(var(--c-ink))',
  fontSize: 12,
};

export function RiskDistributionChart({ data }: { data: Array<{ name: string; value: number }> }) {
  if (!data.some((item) => item.value > 0)) return <EmptyState title="No risk data yet" description="Complete a scan to see risk distribution." />;
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--c-line))" vertical={false} />
          <XAxis dataKey="name" tick={axis} tickLine={false} axisLine={false} />
          <YAxis tick={axis} tickLine={false} axisLine={false} allowDecimals={false} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgb(var(--c-elevated))' }} />
          <Bar dataKey="value" name="Analyses" radius={[6, 6, 0, 0]} maxBarSize={48}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.name.toLowerCase().includes('high') ? '#ef4444' : entry.name.toLowerCase().includes('medium') ? '#f59e0b' : entry.name.toLowerCase().includes('low') ? '#10b981' : '#06b6d4'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ScanTrendChart({ data }: { data: Array<{ date: string; count: number }> }) {
  if (!data.length) return <EmptyState title="No trend data yet" description="Activity will appear after your first analysis." />;
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="scanGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--c-line))" vertical={false} />
          <XAxis dataKey="date" tick={axis} tickLine={false} axisLine={false} />
          <YAxis tick={axis} tickLine={false} axisLine={false} allowDecimals={false} />
          <Tooltip contentStyle={tooltipStyle} />
          <Area type="monotone" dataKey="count" name="Scans" stroke="#06b6d4" strokeWidth={2} fill="url(#scanGradient)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DonutChart({
  data,
  colors = ['#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
  label,
}: {
  data: Array<{ name: string; value: number }>;
  colors?: string[];
  label?: string;
}) {
  if (!data.some((item) => item.value > 0)) return <EmptyState title="No data available" />;
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={80} paddingAngle={3} stroke="none">
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={colors[index % colors.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ fontSize: 11, color: 'rgb(var(--c-muted))' }} />
          {label && <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" fontSize="20" fontWeight="700" fill="rgb(var(--c-ink))">{label}</text>}
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MiniBars({ data, className }: { data: Array<{ label: string; value: number }>; className?: string }) {
  const max = Math.max(1, ...data.map((item) => item.value));
  return (
    <div className={cx('space-y-2.5', className)}>
      {data.map((item) => (
        <div key={item.label}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="truncate text-muted">{item.label}</span>
            <span className="font-semibold tabular-nums">{item.value}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
            <div className="h-full rounded-full bg-brand-500" style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
