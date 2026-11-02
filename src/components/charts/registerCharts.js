import {
  ArcElement,
  CategoryScale,
  Chart as ChartJS,
  DoughnutController,
  LineElement,
  LineController,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js';

ChartJS.register(ArcElement, CategoryScale, DoughnutController, LineController, LineElement, LinearScale, PointElement, Tooltip);