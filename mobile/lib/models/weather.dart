class WeatherInfo {
  final double tempMin;
  final double tempMax;
  final double humidity;
  final double rainfall;
  final String condition;
  final String date;

  const WeatherInfo({
    required this.tempMin,
    required this.tempMax,
    required this.humidity,
    required this.rainfall,
    required this.condition,
    required this.date,
  });

  double get temperature => (tempMin + tempMax) / 2;

  factory WeatherInfo.fromJson(Map<String, dynamic> json) {
    final date = json['date'] ?? json['log_date'];
    if (date == null) throw const FormatException('Weather date is missing');

    return WeatherInfo(
      tempMin: _readNumber(json['temp_min'], 'temp_min'),
      tempMax: _readNumber(json['temp_max'], 'temp_max'),
      humidity: _readNumber(json['humidity'], 'humidity'),
      rainfall: _readNumber(json['rainfall'], 'rainfall'),
      condition: (json['condition'] ?? '').toString(),
      date: date.toString().substring(0, 10),
    );
  }

  static double _readNumber(dynamic value, String field) {
    if (value is num) return value.toDouble();
    final parsed = double.tryParse(value?.toString() ?? '');
    if (parsed == null) {
      throw FormatException('Weather field ' + field + ' is missing or invalid');
    }
    return parsed;
  }
}
