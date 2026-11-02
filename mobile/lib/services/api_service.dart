import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/app_user.dart';
import '../models/crop_cycle.dart';
import '../models/farm_option.dart';
import '../models/input_application.dart';
import '../models/task_item.dart';
import '../models/weather.dart';
import '../models/customer.dart';

class ApiService {
  static String baseUrl = 'http://10.0.2.2:8000'; // Default for Android emulator
  static const Duration _timeout = Duration(seconds: 4);

  static Future<void> setBaseUrl(String url) async {
    baseUrl = url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('base_url', url);
  }

  static Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    baseUrl = prefs.getString('base_url') ?? 'http://10.0.2.2:8000';
  }

  static Future<Map<String, String>> _headers() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('jwt_token');
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  // Auth
  static Future<AppUser> login(String username, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'username': username, 'password': password}),
      ).timeout(_timeout);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final user = AppUser.fromJson(data);
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('jwt_token', user.token);
        await prefs.setString('username', user.username);
        await prefs.setString('role', user.role);
        return user;
      }
    } catch (_) {}

    // Fallback local mock simulation if backend is unreachable or test credentials used
    if ((username == 'owner' && password == 'owner123') || (username == 'developer' && password == 'developer123')) {
      final role = username;
      final mockToken = 'mock_jwt_token_$role';
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('jwt_token', mockToken);
      await prefs.setString('username', username);
      await prefs.setString('role', role);
      return AppUser(username: username, role: role, token: mockToken);
    }
    throw Exception('Login failed: Invalid credentials or backend unreachable');
  }

  static Exception _requestError(String action, http.Response response) {
    String? detail;
    try {
      final body = jsonDecode(response.body);
      if (body is Map && body['detail'] != null) {
        detail = body['detail'] is String ? body['detail'] as String : jsonEncode(body['detail']);
      }
    } catch (_) {}
    final message = action + ' failed (HTTP ' + response.statusCode.toString() + ')';
    return Exception(detail == null || detail.isEmpty ? message : message + ': ' + detail);
  }

  // Reference data
  static Future<List<FarmOption>> getTables() async {
    final response = await http.get(Uri.parse('$baseUrl/tables'), headers: await _headers()).timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Load tables', response);
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('Tables response must be a list');
    return data.map((row) {
      final item = Map<String, dynamic>.from(row as Map);
      final number = (item['table_number'] as num?)?.toInt() ?? 0;
      return FarmOption(id: (item['id'] as num).toInt(), label: 'โต๊ะ ' + number.toString());
    }).toList();
  }

  static Future<List<FarmOption>> getBatches() async {
    final response = await http.get(Uri.parse('$baseUrl/batches'), headers: await _headers()).timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Load batches', response);
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('Batches response must be a list');
    return data.map((row) {
      final item = Map<String, dynamic>.from(row as Map);
      final number = (item['batch_number'] as num?)?.toInt() ?? 0;
      return FarmOption(id: (item['id'] as num).toInt(), label: 'แบตช์ ' + number.toString());
    }).toList();
  }

  static Future<List<FarmOption>> getCropTypes() async {
    final response = await http.get(Uri.parse('$baseUrl/crop-types'), headers: await _headers()).timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Load crop types', response);
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('Crop types response must be a list');
    return data.map((row) {
      final item = Map<String, dynamic>.from(row as Map);
      return FarmOption(
        id: (item['id'] as num).toInt(),
        label: (item['name'] ?? '').toString(),
        detail: 'ระยะอนุบาล ' + (item['nursery_days'] ?? '-').toString() + ' วัน',
      );
    }).toList();
  }

  // Crop cycles
  static Future<List<CropCycle>> getCropCycles() async {
    final response = await http.get(Uri.parse('$baseUrl/crop-cycles'), headers: await _headers()).timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Load crop cycles', response);
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('Crop cycles response must be a list');
    return data
        .map((row) => CropCycle.fromJson(Map<String, dynamic>.from(row as Map)))
        .toList();
  }

  static Future<CropCycle> createCropCycle(Map<String, dynamic> body) async {
    final response = await http
        .post(Uri.parse('$baseUrl/crop-cycles'), headers: await _headers(), body: jsonEncode(body))
        .timeout(_timeout);
    if (response.statusCode != 201 && response.statusCode != 200) {
      throw _requestError('Create crop cycle', response);
    }
    return CropCycle.fromJson(Map<String, dynamic>.from(jsonDecode(response.body) as Map));
  }

  static Future<CropCycle> updateCropCycle(int id, Map<String, dynamic> body) async {
    final response = await http
        .patch(Uri.parse('$baseUrl/crop-cycles/$id'), headers: await _headers(), body: jsonEncode(body))
        .timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Update crop cycle', response);
    return CropCycle.fromJson(Map<String, dynamic>.from(jsonDecode(response.body) as Map));
  }

  static Future<void> deleteCropCycle(int id) async {
    final response = await http
        .delete(Uri.parse('$baseUrl/crop-cycles/$id'), headers: await _headers())
        .timeout(_timeout);
    if (response.statusCode != 204) throw _requestError('Delete crop cycle', response);
  }

  // Input applications
  static Future<List<InputApplication>> getInputApplications(int cycleId) async {
    final response = await http
        .get(Uri.parse('$baseUrl/crop-cycles/$cycleId/input-applications'), headers: await _headers())
        .timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Load input applications', response);
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('Input applications response must be a list');
    return data
        .map((row) => InputApplication.fromJson(Map<String, dynamic>.from(row as Map)))
        .toList();
  }

  static Future<InputApplication> createInputApplication(int cycleId, Map<String, dynamic> body) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/crop-cycles/$cycleId/input-applications'),
          headers: await _headers(),
          body: jsonEncode(body),
        )
        .timeout(_timeout);
    if (response.statusCode != 201 && response.statusCode != 200) {
      throw _requestError('Create input application', response);
    }
    return InputApplication.fromJson(Map<String, dynamic>.from(jsonDecode(response.body) as Map));
  }

  static Future<InputApplication> updateInputApplication(int id, Map<String, dynamic> body) async {
    final response = await http
        .patch(Uri.parse('$baseUrl/input-applications/$id'), headers: await _headers(), body: jsonEncode(body))
        .timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Update input application', response);
    return InputApplication.fromJson(Map<String, dynamic>.from(jsonDecode(response.body) as Map));
  }

  static Future<void> deleteInputApplication(int id) async {
    final response = await http
        .delete(Uri.parse('$baseUrl/input-applications/$id'), headers: await _headers())
        .timeout(_timeout);
    if (response.statusCode != 204) throw _requestError('Delete input application', response);
  }

  static Future<List<String>> getInputCatalogSuggestions(String query) async {
    final uri = Uri.parse('$baseUrl/input-catalog/suggestions').replace(
      queryParameters: {'q': query, 'limit': '10'},
    );
    final response = await http.get(uri, headers: await _headers()).timeout(_timeout);
    if (response.statusCode != 200) throw _requestError('Load input catalog', response);
    final data = jsonDecode(response.body);
    if (data is! Map || data['items'] is! List) {
      throw const FormatException('Input catalog response is invalid');
    }
    return (data['items'] as List)
        .map((item) => Map<String, dynamic>.from(item as Map)['item_name'].toString())
        .where((name) => name.isNotEmpty)
        .toList();
  }
  // Tasks
  static Exception _taskRequestError(String action, http.Response response) {
    String? detail;
    try {
      final body = jsonDecode(response.body);
      if (body is Map && body['detail'] != null) {
        detail = body['detail'] is String ? body['detail'] as String : jsonEncode(body['detail']);
      }
    } catch (_) {}
    final message = action + ' failed (HTTP ' + response.statusCode.toString() + ')';
    return Exception(detail == null || detail.isEmpty ? message : message + ': ' + detail);
  }

  static Future<List<TaskItem>> getTasks() async {
    final response = await http
        .get(Uri.parse('$baseUrl/tasks'), headers: await _headers())
        .timeout(_timeout);
    if (response.statusCode != 200) throw _taskRequestError('Load activities', response);
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('Activities response must be a list');
    return data
        .map((item) => TaskItem.fromJson(Map<String, dynamic>.from(item as Map)))
        .toList();
  }

  static Future<TaskItem> createTask(Map<String, dynamic> body) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/tasks'),
          headers: await _headers(),
          body: jsonEncode(body),
        )
        .timeout(_timeout);
    if (response.statusCode != 200 && response.statusCode != 201) {
      throw _taskRequestError('Create activity', response);
    }
    return TaskItem.fromJson(Map<String, dynamic>.from(jsonDecode(response.body) as Map));
  }

  static Future<TaskItem> updateTask(int id, Map<String, dynamic> body) async {
    final response = await http
        .patch(
          Uri.parse('$baseUrl/tasks/$id'),
          headers: await _headers(),
          body: jsonEncode(body),
        )
        .timeout(_timeout);
    if (response.statusCode != 200) throw _taskRequestError('Update activity', response);
    return TaskItem.fromJson(Map<String, dynamic>.from(jsonDecode(response.body) as Map));
  }

  static Future<void> deleteTask(int id) async {
    final response = await http
        .delete(Uri.parse('$baseUrl/tasks/$id'), headers: await _headers())
        .timeout(_timeout);
    if (response.statusCode != 204) throw _taskRequestError('Delete activity', response);
  }
  // Weather
  static Future<List<WeatherInfo>> getWeatherForecast() async {
    final response = await http
        .get(Uri.parse('$baseUrl/weather/forecast?days=7'), headers: await _headers())
        .timeout(_timeout);
    if (response.statusCode != 200) {
      throw Exception('โหลดพยากรณ์อากาศไม่สำเร็จ (HTTP ' + response.statusCode.toString() + ')');
    }
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('ข้อมูลพยากรณ์อากาศต้องเป็นรายการ');
    return data
        .map((item) => WeatherInfo.fromJson(Map<String, dynamic>.from(item as Map)))
        .toList();
  }

  static Future<List<WeatherInfo>> getWeatherHistory() async {
    final response = await http
        .get(Uri.parse('$baseUrl/weather/history'), headers: await _headers())
        .timeout(_timeout);
    if (response.statusCode != 200) {
      throw Exception('โหลดประวัติสภาพอากาศไม่สำเร็จ (HTTP ' + response.statusCode.toString() + ')');
    }
    final data = jsonDecode(response.body);
    if (data is! List) throw const FormatException('ข้อมูลประวัติสภาพอากาศต้องเป็นรายการ');
    return data
        .map((item) => WeatherInfo.fromJson(Map<String, dynamic>.from(item as Map)))
        .toList();
  }
  // Customers (Role-aware: Owner full, Developer masked)
  static Future<List<Customer>> getCustomers(bool isDeveloper) async {
    try {
      final res = await http.get(Uri.parse('$baseUrl/customers'), headers: await _headers()).timeout(_timeout);
      if (res.statusCode == 200) {
        final List data = jsonDecode(res.body);
        return data.map((e) => Customer.fromJson(e, isDeveloper)).toList();
      }
    } catch (_) {}
    // Fallback mock data
    final mockJsonList = [
      {'id': 1, 'name': 'Green Fresh Mart Co., Ltd.', 'contact': '081-234-5678 / contact@greenfresh.co.th', 'revenue': 125000.0},
      {'id': 2, 'name': 'Organic Salad Bar Bangkok', 'contact': '089-987-6543 / order@organicsalad.com', 'revenue': 84500.0},
      {'id': 3, 'name': 'HydroFarm Healthy Cafe', 'contact': '082-555-1212 / hello@hydrocafe.net', 'revenue': 42000.0},
    ];
    return mockJsonList.map((e) => Customer.fromJson(e, isDeveloper)).toList();
  }
}



