import { Doughnut } from 'react-chartjs-2';
import './registerCharts';

function DoughnutChart({ data, options = {} }) {
  return (
    <Doughnut
      data={data}
      options={{
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => `${context.label}: ${context.formattedValue}`,
            },
          },
        },
        ...options,
      }}
    />
  );
}

export default DoughnutChart;