class TaskItem {
  final int id;
  final String title;
  final String dueDate;
  final String status;
  final String source;

  const TaskItem({
    required this.id,
    required this.title,
    required this.dueDate,
    required this.status,
    required this.source,
  });

  bool get isCompleted {
    final normalized = status.toLowerCase();
    return normalized == 'done' || normalized == 'completed';
  }

  factory TaskItem.fromJson(Map<String, dynamic> json) {
    final id = json['id'];
    if (id is! num) throw const FormatException('Task id is missing or invalid');

    return TaskItem(
      id: id.toInt(),
      title: (json['title'] ?? '').toString(),
      dueDate: (json['due_date'] ?? '').toString(),
      status: (json['status'] ?? 'pending').toString(),
      source: (json['source'] ?? 'manual').toString(),
    );
  }
}
