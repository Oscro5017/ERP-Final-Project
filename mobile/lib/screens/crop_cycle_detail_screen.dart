import 'package:flutter/material.dart';
import '../models/crop_cycle.dart';
import '../models/input_application.dart';
import '../services/api_service.dart';
import 'input_application_form_sheet.dart';

class CropCycleDetailScreen extends StatefulWidget {
  final CropCycle cycle;
  const CropCycleDetailScreen({super.key, required this.cycle});

  @override
  State<CropCycleDetailScreen> createState() => _CropCycleDetailScreenState();
}

class _CropCycleDetailScreenState extends State<CropCycleDetailScreen> {
  late CropCycle _cycle;
  late final TextEditingController _harvestQuantityController;
  bool _isLoading = true;
  bool _isSaving = false;
  List<InputApplication> _inputs = [];
  String? _inputError;

  @override
  void initState() {
    super.initState();
    _cycle = widget.cycle;
    _harvestQuantityController = TextEditingController(
      text: _cycle.harvestQuantityKg?.toString() ?? '',
    );
    _loadInputs();
  }

  @override
  void dispose() {
    _harvestQuantityController.dispose();
    super.dispose();
  }

  Future<void> _loadInputs() async {
    if (mounted) setState(() => _isLoading = true);
    try {
      final inputs = await ApiService.getInputApplications(_cycle.id);
      if (mounted) {
        setState(() {
          _inputs = inputs;
          _inputError = null;
          _isLoading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _inputs = [];
          _inputError = error.toString().replaceFirst('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _showAddInputForm() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => InputApplicationFormSheet(
        cycleLabel: _cycle.cycleCode,
        onSave: (body) async {
          await ApiService.createInputApplication(_cycle.id, body);
          await _loadInputs();
        },
      ),
    );
  }

  Future<void> _updateStatus(String status) async {
    if (status == _cycle.status || _isSaving) return;
    setState(() => _isSaving = true);
    try {
      final updated = await ApiService.updateCropCycle(_cycle.id, {'status': status});
      if (mounted) setState(() => _cycle = updated);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('เปลี่ยนสถานะไม่สำเร็จ: ' + error.toString())),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  Future<void> _saveHarvestQuantity() async {
    if (_isSaving) return;
    final raw = _harvestQuantityController.text.trim();
    final quantity = raw.isEmpty ? null : double.tryParse(raw);
    if (raw.isNotEmpty && (quantity == null || quantity < 0)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('กรอกน้ำหนักเก็บเกี่ยวเป็นตัวเลขตั้งแต่ 0 ขึ้นไป')),
      );
      return;
    }

    setState(() => _isSaving = true);
    try {
      final updated = await ApiService.updateCropCycle(
        _cycle.id,
        {'harvest_quantity_kg': quantity},
      );
      if (mounted) {
        setState(() => _cycle = updated);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('บันทึกน้ำหนักเก็บเกี่ยวแล้ว')),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('บันทึกไม่สำเร็จ: ' + error.toString())),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  String _statusLabel(String status) {
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const statuses = ['nursery', 'bushed', 'ready_to_harvest', 'harvested', 'empty'];

    return Scaffold(
      appBar: AppBar(
        title: Text(_cycle.cycleCode),
        backgroundColor: Colors.green.shade700,
        foregroundColor: Colors.white,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('รายละเอียดรอบปลูก', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                  const Divider(height: 24),
                  Text('ชนิดพืช: ' + _cycle.cropTypeName),
                  const SizedBox(height: 6),
                  Text('โต๊ะ: ' + _cycle.tableNumber.toString()),
                  const SizedBox(height: 6),
                  Text('แบตช์: ' + _cycle.batchNumber.toString()),
                  const SizedBox(height: 6),
                  Text('เริ่มอนุบาล: ' + _cycle.nurseryStart),
                  if (_cycle.transplantDate != null) ...[
                    const SizedBox(height: 6),
                    Text('วันที่ย้ายปลูก: ' + _cycle.transplantDate!),
                  ],
                  if (_cycle.harvestDate != null) ...[
                    const SizedBox(height: 6),
                    Text('วันที่เก็บเกี่ยว: ' + _cycle.harvestDate!),
                  ],
                  const SizedBox(height: 6),
                  Text('สถานะ: ' + _statusLabel(_cycle.status)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('เปลี่ยนสถานะรอบปลูก', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: statuses
                .map((status) => ChoiceChip(
                      label: Text(_statusLabel(status)),
                      selected: _cycle.status == status,
                      onSelected: _isSaving ? null : (_) => _updateStatus(status),
                    ))
                .toList(),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('ผลผลิตที่เก็บได้', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _harvestQuantityController,
                    enabled: !_isSaving,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'น้ำหนัก (กก.)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 8),
                  FilledButton(
                    onPressed: _isSaving ? null : _saveHarvestQuantity,
                    child: const Text('บันทึกน้ำหนัก'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  'บันทึกปุ๋ย/ยา',
                  style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                ),
              ),
              IconButton(
                tooltip: 'เพิ่มบันทึก',
                onPressed: _showAddInputForm,
                icon: const Icon(Icons.add_circle, color: Colors.green),
              ),
            ],
          ),
          if (_isLoading)
            const Center(child: CircularProgressIndicator())
          else if (_inputError != null)
            Card(
              child: ListTile(
                title: Text(_inputError!),
                trailing: IconButton(onPressed: _loadInputs, icon: const Icon(Icons.refresh)),
              ),
            )
          else if (_inputs.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('ยังไม่มีบันทึกปุ๋ย/ยาในรอบนี้'),
              ),
            )
          else
            ..._inputs.map(_applicationCard),
        ],
      ),
    );
  }

  Widget _applicationCard(InputApplication application) => Card(
        margin: const EdgeInsets.only(bottom: 8),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(application.category.isEmpty ? 'ปัจจัยการผลิต' : application.category,
                  style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              Text('วันที่ ' + application.appliedDate),
              if (application.note != null && application.note!.isNotEmpty) Text(application.note!),
              const Divider(),
              for (final item in application.items)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.science, color: Colors.green),
                  title: Text(item.isMasked ? 'ข้อมูลถูกปกปิด' : item.itemName),
                  trailing: Text(item.isMasked ? '••••' : item.quantity + (item.unit.isEmpty ? '' : ' ' + item.unit)),
                ),
            ],
          ),
        ),
      );
}
