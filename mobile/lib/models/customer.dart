class Customer {
  final int id;
  final String name;
  final String contact;
  final double revenue;
  final bool isMasked;

  Customer({
    required this.id,
    required this.name,
    required this.contact,
    required this.revenue,
    this.isMasked = false,
  });

  factory Customer.fromJson(Map<String, dynamic> json, bool isDeveloper) {
    final rawName = json['name'] ?? json['customer_name'] ?? 'Customer #${json['id']}';
    final rawContact = json['contact'] ?? json['phone'] ?? json['email'] ?? 'N/A';
    final rawRevenue = (json['revenue'] as num?)?.toDouble() ?? 0.0;

    if (isDeveloper) {
      return Customer(
        id: json['id'] ?? 0,
        name: json['masked_name'] ?? '████████ (Masked for Dev)',
        contact: json['masked_contact'] ?? '███-███-████',
        revenue: 0.0, // Hidden or zeroed for developer
        isMasked: true,
      );
    }

    return Customer(
      id: json['id'] ?? 0,
      name: rawName,
      contact: rawContact,
      revenue: rawRevenue,
      isMasked: false,
    );
  }
}
