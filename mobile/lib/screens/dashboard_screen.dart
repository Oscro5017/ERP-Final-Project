import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../models/crop_cycle.dart';
import '../models/customer.dart';
import '../models/task_item.dart';
import '../models/weather.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _isLoading = true;
  List<CropCycle> _cycles = [];
  List<TaskItem> _tasks = [];
  WeatherInfo? _weather;
  double _totalRevenue = 0.0;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);
    final auth = Provider.of<AuthProvider>(context, listen: false);
    try {
      final cyclesFuture = ApiService.getCropCycles();
      final tasksFuture = ApiService.getTasks();
      final weatherFuture = ApiService.getWeatherForecast();
      final customersFuture = ApiService.getCustomers(auth.isDeveloper);

      final results = await Future.wait([
        cyclesFuture,
        tasksFuture,
        weatherFuture,
        customersFuture,
      ]);

      _cycles = results[0] as List<CropCycle>;
      _tasks = results[1] as List<TaskItem>;
      final forecast = results[2] as List<WeatherInfo>;
      _weather = forecast.isEmpty ? null : forecast.first;

      final customers = results[3] as List<Customer>;
      if (auth.isOwner) {
        _totalRevenue = customers.fold<double>(
          0.0,
          (sum, customer) => sum + customer.revenue,
        );
      } else {
        _totalRevenue = 0.0;
      }
    } catch (_) {}
    if (mounted) setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    final auth = Provider.of<AuthProvider>(context);
    final theme = Theme.of(context);

    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    final activeCropsCount = _cycles.where((cycle) => cycle.isActive).length;
    final pendingTasksCount = _tasks.where((t) => !t.isCompleted).length;

    return RefreshIndicator(
      onRefresh: _loadData,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Welcome Banner & Role Badge
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [Colors.green.shade700, Colors.green.shade500],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Welcome, ${auth.user?.username ?? "User"}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Role: ${auth.user?.role.toUpperCase()}',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.9),
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
                Chip(
                  label: Text(
                    auth.isOwner ? 'Owner Mode' : 'Developer Mode',
                    style: TextStyle(
                      color: Colors.green.shade800,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  backgroundColor: Colors.white,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Farm Overview (ภาพรวมฟาร์ม)',
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          // Summary Grid
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 1.3,
            children: [
              _buildSummaryCard(
                context,
                title: 'Active Crop Cycles',
                value: '$activeCropsCount / ${_cycles.length}',
                icon: Icons.eco,
                color: Colors.green,
              ),
              _buildSummaryCard(
                context,
                title: 'Pending Tasks',
                value: '$pendingTasksCount',
                icon: Icons.task_alt,
                color: Colors.orange,
              ),
              _buildSummaryCard(
                context,
                title: 'Farm Weather',
                value: _weather != null ? '${_weather!.temperature}°C' : 'N/A',
                subtitle: _weather?.condition,
                icon: Icons.wb_sunny,
                color: Colors.amber,
              ),
              _buildSummaryCard(
                context,
                title: 'Revenue Summary',
                value: auth.isOwner
                    ? '฿${_totalRevenue.toStringAsFixed(0)}'
                    : '██████ (Masked)',
                subtitle: auth.isOwner
                    ? 'Total from customers'
                    : 'Restricted for dev',
                icon: Icons.payments,
                color: auth.isOwner ? Colors.blue : Colors.grey,
              ),
            ],
          ),
          const SizedBox(height: 20),
          Text(
            'Recent Crop Cycles',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          ..._cycles
              .take(3)
              .map(
                (cycle) => Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: Colors.green.shade100,
                      child: Icon(Icons.grass, color: Colors.green.shade800),
                    ),
                    title: Text(
                      cycle.cycleCode,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    subtitle: Text(
                      'โต๊ะ ${cycle.tableNumber} • เริ่มเพาะ ${cycle.nurseryStart}',
                    ),
                    trailing: Chip(
                      label: Text(
                        cycle.status,
                        style: const TextStyle(fontSize: 11),
                      ),
                      backgroundColor: cycle.isActive
                          ? Colors.green.shade50
                          : Colors.grey.shade200,
                    ),
                  ),
                ),
              ),
        ],
      ),
    );
  }

  Widget _buildSummaryCard(
    BuildContext context, {
    required String title,
    required String value,
    String? subtitle,
    required IconData icon,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.grey.withOpacity(0.1),
            blurRadius: 6,
            offset: const Offset(0, 3),
          ),
        ],
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 20),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(color: Colors.grey.shade700, fontSize: 12),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const Spacer(),
          Text(
            value,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 2),
            Text(
              subtitle,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 10),
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}
