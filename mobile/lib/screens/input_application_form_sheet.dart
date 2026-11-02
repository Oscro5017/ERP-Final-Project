import 'package:flutter/material.dart';

class InputApplicationFormSheet extends StatefulWidget {
  final String cycleLabel;
  final Future<void> Function(Map<String, dynamic> body) onSave;

  const InputApplicationFormSheet({
    super.key,
    required this.cycleLabel,
    required this.onSave,
  });

  @override
  State<InputApplicationFormSheet> createState() => _InputApplicationFormSheetState();
}

class _InputApplicationFormSheetState extends State<InputApplicationFormSheet> {
  late final TextEditingController _nameController;
  late final TextEditingController _quantityController;
  late final TextEditingController _unitController;
  late final TextEditingController _categoryController;
  late final TextEditingController _noteController;
  DateTime _appliedDate = DateTime.now();
  bool _isSaving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController();
    _quantityController = TextEditingController(text: '1');
    _unitController = TextEditingController();
    _categoryController = TextEditingController(text: 'ปุ๋ย');
    _noteController = TextEditingController();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _quantityController.dispose();
    _unitController.dispose();
    _categoryController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  Future<void> _chooseDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _appliedDate,
      firstDate: DateTime(2024),
      lastDate: DateTime(2035),
    );
    if (picked != null && mounted) setState(() => _appliedDate = picked);
  }

  Future<void> _submit() async {
    final itemName = _nameController.text.trim();
    final quantity = double.tryParse(_quantityController.text.trim());
    if (itemName.isEmpty || quantity == null || quantity <= 0) {
      setState(() => _error = 'กรอกชื่อรายการและจำนวนที่มากกว่า 0');
      return;
    }
    setState(() {
      _isSaving = true;
      _error = null;
    });
    final body = {
      'applied_date': _appliedDate.toIso8601String().substring(0, 10),
      'category': _categoryController.text.trim(),
      'note': _noteController.text.trim().isEmpty ? null : _noteController.text.trim(),
      'items': [
        {
          'item_name': itemName,
          'quantity': quantity,
          'unit': _unitController.text.trim(),
        },
      ],
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
                Text('บันทึกปัจจัยการผลิต • ' + widget.cycleLabel,
                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
                const SizedBox(height: 16),
                TextField(
                  controller: _nameController,
                  autofocus: true,
                  decoration: const InputDecoration(labelText: 'ชื่อปุ๋ย/ยา', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      flex: 2,
                      child: TextField(
                        controller: _quantityController,
                        enabled: !_isSaving,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'จำนวน', border: OutlineInputBorder()),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: _unitController,
                        enabled: !_isSaving,
                        decoration: const InputDecoration(labelText: 'หน่วย', border: OutlineInputBorder()),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _categoryController,
                  enabled: !_isSaving,
                  decoration: const InputDecoration(labelText: 'ประเภท', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _noteController,
                  enabled: !_isSaving,
                  decoration: const InputDecoration(labelText: 'หมายเหตุ', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: _isSaving ? null : _chooseDate,
                  icon: const Icon(Icons.calendar_today),
                  label: Text('วันที่ใช้ ' + _appliedDate.toIso8601String().substring(0, 10)),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  Text(_error!, style: const TextStyle(color: Colors.red)),
                ],
                const SizedBox(height: 16),
                ElevatedButton(
                  onPressed: _isSaving ? null : _submit,
                  child: _isSaving
                      ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('บันทึก'),
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
      );
}
