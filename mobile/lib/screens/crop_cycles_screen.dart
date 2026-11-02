import 'package:flutter/material.dart';
import '../models/crop_cycle.dart';
import '../models/farm_option.dart';
import '../services/api_service.dart';
import 'crop_cycle_detail_screen.dart';

const _cycleStatuses = ['nursery', 'bushed', 'ready_to_harvest', 'harvested', 'empty'];

String _cycleStatusLabel(String status) {
  switch (status) {
    case 'nursery':
      return 'อนุบาล';
    case 'bushed':
      return 'ย้ายปลูกแล้ว';
    case 'ready_to_harvest':
      return 'พร้อมเก็บเกี่ยว';
    case 'harvested':
      return 'เก็บเกี่ยวแล้ว';
    case 'empty':
      return 'ว่าง';
    default:
      return status;
  }
}

class CropCyclesScreen extends StatefulWidget {
  const CropCyclesScreen({super.key});

  @override
  State<CropCyclesScreen> createState() => _CropCyclesScreenState();
}

class _CropCyclesScreenState extends State<CropCyclesScreen> {
  bool _isLoading = true;
  List<CropCycle> _cycles = [];
  List<FarmOption> _tables = [];
  List<FarmOption> _batches = [];
  List<FarmOption> _cropTypes = [];
  String? _error;
  String _filterStatus = 'all';

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    if (mounted) setState(() => _isLoading = true);
    try {
      final results = await Future.wait<Object>([
        ApiService.getCropCycles(),
        ApiService.getTables(),
        ApiService.getBatches(),
        ApiService.getCropTypes(),
      ]);
      if (!mounted) return;
      setState(() {
        _cycles = results[0] as List<CropCycle>;
        _tables = results[1] as List<FarmOption>;
        _batches = results[2] as List<FarmOption>;
        _cropTypes = results[3] as List<FarmOption>;
        _error = null;
        _isLoading = false;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error.toString().replaceFirst('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _showAddCycleForm() async {
    if (_tables.isEmpty || _batches.isEmpty || _cropTypes.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('ยังไม่มีข้อมูลโต๊ะ แบตช์ หรือชนิดพืชจากระบบ')),
      );
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _CropCycleFormSheet(
        tables: _tables,
        batches: _batches,
        cropTypes: _cropTypes,
        onSave: (body) async {
          await ApiService.createCropCycle(body);
          await _loadData();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final visibleCycles = _filterStatus == 'all'
        ? _cycles
        : _cycles.where((cycle) => cycle.status == _filterStatus).toList();

    return Scaffold(
      body: Column(
        children: [
          SizedBox(
            height: 58,
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              scrollDirection: Axis.horizontal,
              children: [
                _statusChip('ทั้งหมด', 'all'),
                for (final status in _cycleStatuses)
                  Padding(
                    padding: const EdgeInsets.only(left: 8),
                    child: _statusChip(_cycleStatusLabel(status), status),
                  ),
              ],
            ),
          ),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? _errorView()
                    : visibleCycles.isEmpty
                        ? const Center(child: Text('ไม่พบรอบปลูกจากระบบ'))
                        : RefreshIndicator(
                            onRefresh: _loadData,
                            child: ListView.builder(
                              itemCount: visibleCycles.length,
                              itemBuilder: (context, index) {
                                final cycle = visibleCycles[index];
                                return Card(
                                  margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                                  child: ListTile(
                                    leading: CircleAvatar(
                                      backgroundColor: Colors.green.shade100,
                                      child: Icon(Icons.grass, color: Colors.green.shade800),
                                    ),
                                    title: Text(cycle.cycleCode, style: const TextStyle(fontWeight: FontWeight.bold)),
                                    subtitle: Text(
                                      'โต๊ะ ' + cycle.tableNumber.toString() +
                                          ' • ' + cycle.cropTypeName +
                                          ' • แบตช์ ' + cycle.batchNumber.toString() +
                                          '\nเริ่มอนุบาล ' + cycle.nurseryStart,
                                    ),
                                    isThreeLine: true,
                                    trailing: Chip(
                                      label: Text(_cycleStatusLabel(cycle.status), style: const TextStyle(fontSize: 11)),
                                      backgroundColor: cycle.isActive ? Colors.green.shade50 : Colors.grey.shade200,
                                    ),
                                    onTap: () async {
                                      await Navigator.push(
                                        context,
                                        MaterialPageRoute(builder: (_) => CropCycleDetailScreen(cycle: cycle)),
                                      );
                                      _loadData();
                                    },
                                  ),
                                );
                              },
                            ),
                          ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: Colors.green,
        onPressed: _isLoading ? null : _showAddCycleForm,
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  Widget _statusChip(String label, String value) => ChoiceChip(
        label: Text(label),
        selected: _filterStatus == value,
        onSelected: (_) => setState(() => _filterStatus = value),
      );

  Widget _errorView() => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _loadData,
                icon: const Icon(Icons.refresh),
                label: const Text('ลองโหลดอีกครั้ง'),
              ),
            ],
          ),
        ),
      );
}

class _CropCycleFormSheet extends StatefulWidget {
  final List<FarmOption> tables;
  final List<FarmOption> batches;
  final List<FarmOption> cropTypes;
  final Future<void> Function(Map<String, dynamic> body) onSave;

  const _CropCycleFormSheet({
    required this.tables,
    required this.batches,
    required this.cropTypes,
    required this.onSave,
  });

  @override
  State<_CropCycleFormSheet> createState() => _CropCycleFormSheetState();
}

class _CropCycleFormSheetState extends State<_CropCycleFormSheet> {
  int? _tableId;
  int? _batchId;
  int? _cropTypeId;
  DateTime _nurseryStart = DateTime.now();
  bool _isSaving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _tableId = widget.tables.first.id;
    _batchId = widget.batches.first.id;
    _cropTypeId = widget.cropTypes.first.id;
  }

  Future<void> _chooseDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _nurseryStart,
      firstDate: DateTime(2024),
      lastDate: DateTime(2035),
    );
    if (picked != null && mounted) setState(() => _nurseryStart = picked);
  }

  Future<void> _submit() async {
    if (_tableId == null || _batchId == null || _cropTypeId == null) {
      setState(() => _error = 'กรุณาเลือกโต๊ะ แบตช์ และชนิดพืช');
      return;
    }
    setState(() {
      _isSaving = true;
      _error = null;
    });
    final body = {
      'table_id': _tableId,
      'batch_id': _batchId,
      'crop_type_id': _cropTypeId,
      'nursery_start': _nurseryStart.toIso8601String().substring(0, 10),
      'status': 'nursery',
    };
    try {
      await widget.onSave(body);
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) {
        setState(() {
          _isSaving = false;
          _error = error.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
          left: 16,
          right: 16,
          top: 16,
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('เพิ่มรอบปลูก', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                const SizedBox(height: 16),
                DropdownButtonFormField<int>(
                  initialValue: _tableId,
                  decoration: const InputDecoration(labelText: 'โต๊ะปลูก', border: OutlineInputBorder()),
                  items: widget.tables.map((item) => DropdownMenuItem(value: item.id, child: Text(item.label))).toList(),
                  onChanged: _isSaving ? null : (value) => setState(() => _tableId = value),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int>(
                  initialValue: _batchId,
                  decoration: const InputDecoration(labelText: 'แบตช์', border: OutlineInputBorder()),
                  items: widget.batches.map((item) => DropdownMenuItem(value: item.id, child: Text(item.label))).toList(),
                  onChanged: _isSaving ? null : (value) => setState(() => _batchId = value),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int>(
                  initialValue: _cropTypeId,
                  decoration: const InputDecoration(labelText: 'ชนิดพืช', border: OutlineInputBorder()),
                  items: widget.cropTypes.map((item) => DropdownMenuItem(value: item.id, child: Text(item.label))).toList(),
                  onChanged: _isSaving ? null : (value) => setState(() => _cropTypeId = value),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _isSaving ? null : _chooseDate,
                  icon: const Icon(Icons.calendar_today),
                  label: Text('เริ่มอนุบาล ' + _nurseryStart.toIso8601String().substring(0, 10)),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  Text(_error!, style: const TextStyle(color: Colors.red)),
                ],
                const SizedBox(height: 20),
                ElevatedButton(
                  onPressed: _isSaving ? null : _submit,
                  child: _isSaving
                      ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('สร้างรอบปลูก'),
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
      );
}
