import 'package:flutter/material.dart';

import '../models/task_item.dart';
import '../services/api_service.dart';

class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  bool _isLoading = true;
  List<TaskItem> _tasks = [];
  String? _loadError;
  String _filter = 'all';

  @override
  void initState() {
    super.initState();
    _loadTasks();
  }

  Future<void> _loadTasks({bool showLoading = true}) async {
    if (showLoading && mounted) setState(() => _isLoading = true);
    try {
      final tasks = await ApiService.getTasks();
      if (mounted) {
        setState(() {
          _tasks = tasks;
          _loadError = null;
          _isLoading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _loadError = error.toString().replaceFirst('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _showTaskForm({TaskItem? task}) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _TaskFormSheet(
        task: task,
        onSave: (body) async {
          if (task == null) {
            await ApiService.createTask(body);
          } else {
            await ApiService.updateTask(task.id, body);
          }
          await _loadTasks();
        },
      ),
    );
  }

  Future<void> _toggleTaskStatus(TaskItem task) async {
    final newStatus = task.isCompleted ? 'pending' : 'done';
    try {
      await ApiService.updateTask(task.id, {'status': newStatus});
      await _loadTasks(showLoading: false);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('เปลี่ยนสถานะไม่สำเร็จ: ' + error.toString())),
        );
      }
    }
  }

  Future<void> _deleteTask(TaskItem task) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('ลบกิจกรรมนี้?'),
        content: Text('ต้องการลบ "' + task.title + '" หรือไม่'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('ยกเลิก'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('ลบ'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await ApiService.deleteTask(task.id);
      await _loadTasks(showLoading: false);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('ลบกิจกรรมไม่สำเร็จ: ' + error.toString())),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final today = DateTime.now().toIso8601String().substring(0, 10);
    final filtered = _tasks.where((task) {
      switch (_filter) {
        case 'today':
          return task.dueDate == today;
        case 'pending':
          return !task.isCompleted;
        case 'completed':
          return task.isCompleted;
        default:
          return true;
      }
    }).toList();

    return Scaffold(
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  const Text(
                    'แสดง: ',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  _filterChip('ทั้งหมด', 'all'),
                  const SizedBox(width: 8),
                  _filterChip('วันนี้', 'today'),
                  const SizedBox(width: 8),
                  _filterChip('ค้างอยู่', 'pending'),
                  const SizedBox(width: 8),
                  _filterChip('เสร็จแล้ว', 'completed'),
                ],
              ),
            ),
          ),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _loadError != null
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(_loadError!, textAlign: TextAlign.center),
                          const SizedBox(height: 12),
                          OutlinedButton.icon(
                            onPressed: _loadTasks,
                            icon: const Icon(Icons.refresh),
                            label: const Text('ลองโหลดอีกครั้ง'),
                          ),
                        ],
                      ),
                    ),
                  )
                : filtered.isEmpty
                ? const Center(child: Text('ไม่พบกิจกรรม'))
                : RefreshIndicator(
                    onRefresh: _loadTasks,
                    child: ListView.builder(
                      itemCount: filtered.length,
                      itemBuilder: (context, index) {
                        final task = filtered[index];
                        return Card(
                          margin: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 6,
                          ),
                          child: ListTile(
                            leading: Checkbox(
                              value: task.isCompleted,
                              onChanged: (_) => _toggleTaskStatus(task),
                              activeColor: Colors.green,
                            ),
                            title: Text(
                              task.title,
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                decoration: task.isCompleted
                                    ? TextDecoration.lineThrough
                                    : null,
                                color: task.isCompleted
                                    ? Colors.grey
                                    : Colors.black87,
                              ),
                            ),
                            subtitle: Text('กำหนด: ' + task.dueDate),
                            trailing: PopupMenuButton<String>(
                              tooltip: 'จัดการกิจกรรม',
                              onSelected: (action) {
                                if (action == 'edit') _showTaskForm(task: task);
                                if (action == 'delete') _deleteTask(task);
                              },
                              itemBuilder: (context) => const [
                                PopupMenuItem(
                                  value: 'edit',
                                  child: Text('แก้ไข'),
                                ),
                                PopupMenuItem(
                                  value: 'delete',
                                  child: Text('ลบ'),
                                ),
                              ],
                            ),
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
        onPressed: () => _showTaskForm(),
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  Widget _filterChip(String label, String value) => ChoiceChip(
    label: Text(label),
    selected: _filter == value,
    onSelected: (_) => setState(() => _filter = value),
  );
}

class _TaskFormSheet extends StatefulWidget {
  final TaskItem? task;
  final Future<void> Function(Map<String, dynamic> body) onSave;

  const _TaskFormSheet({required this.task, required this.onSave});

  @override
  State<_TaskFormSheet> createState() => _TaskFormSheetState();
}

class _TaskFormSheetState extends State<_TaskFormSheet> {
  late final TextEditingController _titleController;
  late DateTime _selectedDate;
  bool _isSaving = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController(text: widget.task?.title ?? '');
    _selectedDate =
        DateTime.tryParse(widget.task?.dueDate ?? '') ?? DateTime.now();
  }

  @override
  void dispose() {
    _titleController.dispose();
    super.dispose();
  }

  Future<void> _selectDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate,
      firstDate: DateTime(2024),
      lastDate: DateTime(2035),
    );
    if (picked != null && mounted) setState(() => _selectedDate = picked);
  }

  Future<void> _submit() async {
    final title = _titleController.text.trim();
    if (title.isEmpty) {
      setState(() => _errorMessage = 'กรุณาระบุชื่อกิจกรรม');
      return;
    }

    setState(() {
      _isSaving = true;
      _errorMessage = null;
    });
    final body = {
      'title': title,
      'due_date': _selectedDate.toIso8601String().substring(0, 10),
    };

    try {
      await widget.onSave(body);
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) {
        setState(() {
          _isSaving = false;
          _errorMessage = error.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
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
              Text(
                widget.task == null ? 'เพิ่มกิจกรรม' : 'แก้ไขกิจกรรม',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _titleController,
                autofocus: true,
                maxLength: 200,
                enabled: !_isSaving,
                decoration: const InputDecoration(
                  labelText: 'ชื่อกิจกรรม',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _isSaving ? null : _selectDate,
                icon: const Icon(Icons.calendar_today),
                label: Text(
                  'กำหนดวันที่: ' +
                      _selectedDate.toIso8601String().substring(0, 10),
                ),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: 8),
                Text(_errorMessage!, style: const TextStyle(color: Colors.red)),
              ],
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: _isSaving ? null : _submit,
                child: _isSaving
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(
                        widget.task == null ? 'เพิ่มกิจกรรม' : 'บันทึกการแก้ไข',
                      ),
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}
