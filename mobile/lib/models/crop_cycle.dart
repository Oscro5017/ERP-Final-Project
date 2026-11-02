class CropCycle {
  final int id;
  final String cycleCode;
  final int tableId;
  final int tableNumber;
  final int batchId;
  final int batchNumber;
  final int cropTypeId;
  final String cropTypeName;
  final String status;
  final String nurseryStart;
  final String? transplantDate;
  final String? harvestDate;
  final double? harvestQuantityKg;

  const CropCycle({
    required this.id,
    required this.cycleCode,
    required this.tableId,
    required this.tableNumber,
    required this.batchId,
    required this.batchNumber,
    required this.cropTypeId,
    required this.cropTypeName,
    required this.status,
    required this.nurseryStart,
    this.transplantDate,
    this.harvestDate,
    this.harvestQuantityKg,
  });

  String get name => cycleCode;
  bool get isActive => status != 'harvested' && status != 'empty';

  factory CropCycle.fromJson(Map<String, dynamic> json) {
    final table = Map<String, dynamic>.from(json['table'] as Map? ?? const {});
    final batch = Map<String, dynamic>.from(json['batch'] as Map? ?? const {});
    final cropType = Map<String, dynamic>.from(json['crop_type'] as Map? ?? const {});
    final id = json['id'];
    if (id is! num) throw const FormatException('Crop cycle id is missing or invalid');

    return CropCycle(
      id: id.toInt(),
      cycleCode: (json['cycle_code'] ?? json['name'] ?? '').toString(),
      tableId: _readInt(json['table_id'] ?? table['id']),
      tableNumber: _readInt(table['table_number']),
      batchId: _readInt(json['batch_id'] ?? batch['id']),
      batchNumber: _readInt(batch['batch_number']),
      cropTypeId: _readInt(json['crop_type_id'] ?? cropType['id']),
      cropTypeName: (cropType['name'] ?? json['crop_type_name'] ?? '').toString(),
      status: (json['status'] ?? 'nursery').toString(),
      nurseryStart: (json['nursery_start'] ?? '').toString(),
      transplantDate: json['transplant_date']?.toString(),
      harvestDate: json['harvest_date']?.toString(),
      harvestQuantityKg: (json['harvest_quantity_kg'] as num?)?.toDouble(),
    );
  }

  CropCycle copyWith({String? status, double? harvestQuantityKg}) => CropCycle(
        id: id,
        cycleCode: cycleCode,
        tableId: tableId,
        tableNumber: tableNumber,
        batchId: batchId,
        batchNumber: batchNumber,
        cropTypeId: cropTypeId,
        cropTypeName: cropTypeName,
        status: status ?? this.status,
        nurseryStart: nurseryStart,
        transplantDate: transplantDate,
        harvestDate: harvestDate,
        harvestQuantityKg: harvestQuantityKg ?? this.harvestQuantityKg,
      );

  static int _readInt(dynamic value) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}
