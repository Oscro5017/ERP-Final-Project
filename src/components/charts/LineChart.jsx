import { Line } from 'react-chartjs-2';
import './registerCharts';

function LineChart({ data, options = {}, beginAtZero = true }) {
  return (
    <Line
      data={data}
      options={{
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { mode: 'index', intersect: false },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { family: "'Noto Sans Thai', sans-serif" } },
          },
          y: {
            beginAtZero,
            grid: { color: '#e2e8f0', borderDash: [5, 5] },
            ticks: { font: { family: "'Noto Sans Thai', sans-serif" } },
          },
        },
        ...options,
      }}
    />
  );
}

export default LineChart;