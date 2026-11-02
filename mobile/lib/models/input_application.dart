class InputItemRecord {
  final int id;
  final String itemName;
  final String quantity;
  final String unit;
  final bool isMasked;

  const InputItemRecord({
    required this.id,
    required this.itemName,
    required this.quantity,
    required this.unit,
    required this.isMasked,
  });

  factory InputItemRecord.fromJson(Map<String, dynamic> json) {
    return InputItemRecord(
      id: (json['id'] as num?)?.toInt() ?? 0,
      itemName: (json['item_name'] ?? '').toString(),
      quantity: (json['quantity'] ?? '').toString(),
      unit: (json['unit'] ?? '').toString(),
      isMasked: json['is_masked'] == true,
    );
  }
}

class InputApplication {
  final int id;
  final int cycleId;
  final String appliedDate;
  final String category;
  final String? note;
  final bool isMasked;
  final List<InputItemRecord> items;

  const InputApplication({
    required this.id,
    required this.cycleId,
    required this.appliedDate,
    required this.category,
    required this.items,
    this.note,
    this.isMasked = false,
  });

  factory InputApplication.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return InputApplication(
      id: (json['id'] as num?)?.toInt() ?? 0,
      cycleId: (json['cycle_id'] as num?)?.toInt() ?? 0,
      appliedDate: (json['applied_date'] ?? '').toString(),
      category: (json['category'] ?? '').toString(),
      note: json['note']?.toString(),
      isMasked: json['is_masked'] == true,
      items: rawItems is List
          ? rawItems
              .map((item) => InputItemRecord.fromJson(Map<String, dynamic>.from(item as Map)))
              .toList()
          : const [],
    );
  }
}
