import 'package:flutter/material.dart';
import '../models/weather.dart';
import '../services/api_service.dart';

class WeatherScreen extends StatefulWidget {
  const WeatherScreen({super.key});

  @override
  State<WeatherScreen> createState() => _WeatherScreenState();
}

class _WeatherScreenState extends State<WeatherScreen> {
  bool _isLoading = true;
  List<WeatherInfo> _forecast = [];
  List<WeatherInfo> _history = [];
  List<WeatherInfo> _filteredHistory = [];
  String? _forecastError;
  String? _historyError;
  DateTime? _startDate;
  DateTime? _endDate;

  @override
  void initState() {
    super.initState();
    _loadWeather();
  }

  Future<void> _loadWeather() async {
    if (mounted) {
      setState(() {
        _isLoading = true;
        _forecastError = null;
        _historyError = null;
      });
    }

    final results = await Future.wait([
      ApiService.getWeatherForecast().then<Object?>((value) => value).catchError((Object error) => error),
      ApiService.getWeatherHistory().then<Object?>((value) => value).catchError((Object error) => error),
    ]);

    final forecastResult = results[0];
    if (forecastResult is List<WeatherInfo>) {
      _forecast = forecastResult;
    } else {
      _forecast = [];
      _forecastError = _weatherErrorText(forecastResult);
    }

    final historyResult = results[1];
    if (historyResult is List<WeatherInfo>) {
      _history = List<WeatherInfo>.from(historyResult)
        ..sort((a, b) => b.date.compareTo(a.date));
      _applyDateFilter(notify: false);
      _historyError = null;
    } else {
      _history = [];
      _filteredHistory = [];
      _historyError = _weatherErrorText(historyResult);
    }

    if (mounted) setState(() => _isLoading = false);
  }

  String _weatherErrorText(Object? error) {
    final message = error.toString().replaceFirst('Exception: ', '');
    if (message.contains('SocketException') || message.contains('Failed host lookup')) {
      return 'เชื่อมต่อ Backend ไม่ได้ ตรวจสอบ URL ในเมนูตั้งค่า';
    }
    if (message.contains('TimeoutException')) {
      return 'Backend ไม่ตอบสนองภายในเวลาที่กำหนด';
    }
    return message;
  }

  DateTime? _dateOnly(String value) {
    final parsed = DateTime.tryParse(value);
    if (parsed == null) return null;
    return DateTime(parsed.year, parsed.month, parsed.day);
  }

  void _applyDateFilter({bool notify = true}) {
    final filtered = _history.where((item) {
      final date = _dateOnly(item.date);
      if (date == null) return false;
      final start = _startDate == null ? null : DateTime(_startDate!.year, _startDate!.month, _startDate!.day);
      final end = _endDate == null ? null : DateTime(_endDate!.year, _endDate!.month, _endDate!.day);
      if (start != null && date.isBefore(start)) return false;
      if (end != null && date.isAfter(end)) return false;
      return true;
    }).toList();

    if (notify && mounted) {
      setState(() => _filteredHistory = filtered);
    } else {
      _filteredHistory = filtered;
    }
  }

  void _resetDateFilter() {
    setState(() {
      _startDate = null;
      _endDate = null;
      _filteredHistory = List.from(_history);
    });
  }

  Future<void> _selectDate({required bool isStart}) async {
    final current = isStart ? _startDate : _endDate;
    final picked = await showDatePicker(
      context: context,
      initialDate: current ?? DateTime.now(),
      firstDate: DateTime(2024),
      lastDate: DateTime(2035),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _startDate = picked;
      } else {
        _endDate = picked;
      }
    });
    _applyDateFilter();
  }

  String _dateText(DateTime? value) =>
      value == null ? '' : value.toIso8601String().substring(0, 10);

  String _temperatureRange(WeatherInfo weather) =>
      weather.tempMin.toStringAsFixed(1) + '–' + weather.tempMax.toStringAsFixed(1) + '°C';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final todayForecast = _forecast.isEmpty ? null : _forecast.first;

    if (_isLoading) return const Center(child: CircularProgressIndicator());

    return RefreshIndicator(
      onRefresh: _loadWeather,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
        children: [
          Text('พยากรณ์วันนี้', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          if (todayForecast != null)
            Card(
              color: Colors.green.shade50,
              elevation: 3,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  children: [
                    const Icon(Icons.wb_sunny_rounded, size: 56, color: Colors.amber),
                    const SizedBox(height: 8),
                    Text(_temperatureRange(todayForecast), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.green)),
                    Text(todayForecast.condition, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 12),
                    Text('ความชื้น ' + todayForecast.humidity.toStringAsFixed(1) + '%  •  ฝน ' + todayForecast.rainfall.toStringAsFixed(1) + ' มม.'),
                  ],
                ),
              ),
            )
          else if (_forecastError != null)
            _weatherErrorCard(_forecastError!)
          else
            const Card(child: Padding(padding: EdgeInsets.all(16), child: Text('ยังไม่มีข้อมูลพยากรณ์'))),
          const SizedBox(height: 24),
          Text('พยากรณ์ล่วงหน้า', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          if (_forecast.length <= 1)
            const Card(child: Padding(padding: EdgeInsets.all(16), child: Text('ไม่มีข้อมูลวันถัดไป')))
          else
            ..._forecast.skip(1).map((day) => Card(
                  child: ListTile(
                    leading: const Icon(Icons.cloud_outlined, color: Colors.blueGrey),
                    title: Text(day.date),
                    subtitle: Text(day.condition + ' • ความชื้น ' + day.humidity.toStringAsFixed(1) + '% • ฝน ' + day.rainfall.toStringAsFixed(1) + ' มม.'),
                    trailing: Text(_temperatureRange(day), textAlign: TextAlign.end),
                  ),
                )),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text('บันทึกย้อนหลัง', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
              ),
              if (_startDate != null || _endDate != null)
                TextButton.icon(
                  onPressed: _resetDateFilter,
                  icon: const Icon(Icons.refresh, size: 14),
                  label: const Text('รีเซ็ต'),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _selectDate(isStart: true),
                      icon: const Icon(Icons.calendar_today, size: 16),
                      label: Text(_startDate == null ? 'จากวันที่' : _dateText(_startDate)),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _selectDate(isStart: false),
                      icon: const Icon(Icons.calendar_today, size: 16),
                      label: Text(_endDate == null ? 'ถึงวันที่' : _dateText(_endDate)),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          if (_historyError != null)
            _weatherErrorCard(_historyError!)
          else if (_filteredHistory.isEmpty)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text('ไม่พบข้อมูลบันทึกในช่วงวันที่เลือก'),
              ),
            )
          else
            ..._filteredHistory.map((day) => Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: const Icon(Icons.thermostat, color: Colors.orange),
                    title: Text('วันที่: ' + day.date, style: const TextStyle(fontWeight: FontWeight.bold)),
                    subtitle: Text(day.condition + ' • ความชื้น ' + day.humidity.toStringAsFixed(1) + '% • ฝน ' + day.rainfall.toStringAsFixed(1) + ' มม.'),
                    trailing: Text(_temperatureRange(day), textAlign: TextAlign.end),
                  ),
                )),
        ],
      ),
    );
  }

  Widget _weatherErrorCard(String message) => Card(
        color: Colors.orange.shade50,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Icon(Icons.cloud_off, color: Colors.deepOrange),
              const SizedBox(width: 12),
              Expanded(child: Text(message)),
              IconButton(tooltip: 'ลองใหม่', onPressed: _loadWeather, icon: const Icon(Icons.refresh)),
            ],
          ),
        ),
      );
}
