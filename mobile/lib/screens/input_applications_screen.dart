import 'package:flutter/material.dart';
import '../models/crop_cycle.dart';
import '../models/input_application.dart';
import '../services/api_service.dart';
import 'input_application_form_sheet.dart';

class InputApplicationsScreen extends StatefulWidget {
  const InputApplicationsScreen({super.key});

  @override
  State<InputApplicationsScreen> createState() => _InputApplicationsScreenState();
}

class _InputApplicationsScreenState extends State<InputApplicationsScreen> {
  bool _isLoading = true;
  List<CropCycle> _cycles = [];
  CropCycle? _selectedCycle;
  List<InputApplication> _inputs = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadCycles();
  }

  Future<void> _loadCycles() async {
    if (mounted) setState(() => _isLoading = true);
    try {
      final cycles = await ApiService.getCropCycles();
      if (!mounted) return;
      setState(() {
        _cycles = cycles;
        _selectedCycle = cycles.isEmpty ? null : cycles.first;
        _error = null;
      });
      if (_selectedCycle != null) {
        await _loadInputs(_selectedCycle!.id);
      } else if (mounted) {
        setState(() {
          _inputs = [];
          _isLoading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error.toString().replaceFirst('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _loadInputs(int cycleId) async {
    if (mounted) setState(() => _isLoading = true);
    try {
      final inputs = await ApiService.getInputApplications(cycleId);
      if (mounted) {
        setState(() {
          _inputs = inputs;
          _error = null;
          _isLoading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _inputs = [];
          _error = error.toString().replaceFirst('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _showAddInputForm() async {
    final cycle = _selectedCycle;
    if (cycle == null) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => InputApplicationFormSheet(
        cycleLabel: cycle.cycleCode,
        onSave: (body) async {
          await ApiService.createInputApplication(cycle.id, body);
          await _loadInputs(cycle.id);
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          if (_cycles.isNotEmpty)
            Padding(
              padding: const EdgeInsets.all(12),
              child: DropdownButtonFormField<int>(
                value: _selectedCycle?.id,
                decoration: const InputDecoration(labelText: 'เลือกรอบปลูก', border: OutlineInputBorder()),
                items: _cycles
                    .map((cycle) => DropdownMenuItem(
                          value: cycle.id,
                          child: Text(cycle.cycleCode + ' • โต๊ะ ' + cycle.tableNumber.toString()),
                        ))
                    .toList(),
                onChanged: (id) {
                  final matches = _cycles.where((cycle) => cycle.id == id);
                  final selected = matches.isEmpty ? null : matches.first;
                  if (selected != null) {
                    setState(() {
                      _selectedCycle = selected;
                      _error = null;
                    });
                    _loadInputs(selected.id);
                  }
                },
              ),
            ),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(_error!, textAlign: TextAlign.center),
                              const SizedBox(height: 12),
                              OutlinedButton.icon(
                                onPressed: _selectedCycle == null ? _loadCycles : () => _loadInputs(_selectedCycle!.id),
                                icon: const Icon(Icons.refresh),
                                label: const Text('ลองอีกครั้ง'),
                              ),
                            ],
                          ),
                        ),
                      )
                    : _selectedCycle == null
                        ? const Center(child: Text('เพิ่มรอบปลูกก่อนจึงจะบันทึกปัจจัยการผลิตได้'))
                        : _inputs.isEmpty
                            ? const Center(child: Text('ยังไม่มีบันทึกปัจจัยการผลิตในรอบนี้'))
                            : RefreshIndicator(
                                onRefresh: () => _loadInputs(_selectedCycle!.id),
                                child: ListView.builder(
                                  itemCount: _inputs.length,
                                  itemBuilder: (context, index) => _applicationCard(_inputs[index]),
                                ),
                              ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: Colors.green,
        onPressed: _isLoading || _selectedCycle == null ? null : _showAddInputForm,
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  Widget _applicationCard(InputApplication application) => Card(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
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
