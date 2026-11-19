import React from 'react';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  CartesianGrid, XAxis, YAxis, Tooltip, Legend,
} from 'recharts';

const palette = ['#4cc9f0', '#4361ee', '#f0b429', '#ff5c72', '#2ecc71', '#b388ff', '#ff8fab'];

export function TimeSeriesChart({ data, height = 240 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data || []}>
        <CartesianGrid stroke="#22314d" strokeDasharray="3 3" />
        <XAxis dataKey="date" tickLine={false} />
        <YAxis allowDecimals={false} tickLine={false} width={34} />
        <Tooltip contentStyle={{ background: '#111b2e', border: '1px solid #22314d', borderRadius: 8 }} />
        <Line type="monotone" dataKey="count" name="Events" stroke="#4cc9f0" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function DistributionChart({ data, height = 240 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data || []} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78} paddingAngle={2}>
          {(data || []).map((entry, index) => <Cell key={entry.name || index} fill={palette[index % palette.length]} />)}
        </Pie>
        <Tooltip contentStyle={{ background: '#111b2e', border: '1px solid #22314d', borderRadius: 8 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function BarDistribution({ data, height = 240, color = '#4361ee' }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data || []} layout="vertical" margin={{ left: 10 }}>
        <CartesianGrid stroke="#22314d" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" allowDecimals={false} tickLine={false} />
        <YAxis type="category" dataKey="name" width={105} tickLine={false} tick={{ fontSize: 10 }} />
        <Tooltip contentStyle={{ background: '#111b2e', border: '1px solid #22314d', borderRadius: 8 }} />
        <Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
