import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../models/customer.dart';
import '../services/api_service.dart';

class CustomerScreen extends StatefulWidget {
  const CustomerScreen({super.key});

  @override
  State<CustomerScreen> createState() => _CustomerScreenState();
}

class _CustomerScreenState extends State<CustomerScreen> {
  bool _isLoading = true;
  List<Customer> _customers = [];

  @override
  void initState() {
    super.initState();
    _loadCustomers();
  }

  Future<void> _loadCustomers() async {
    setState(() => _isLoading = true);
    final auth = Provider.of<AuthProvider>(context, listen: false);
    try {
      _customers = await ApiService.getCustomers(auth.isDeveloper);
    } catch (_) {}
    if (mounted) setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    final auth = Provider.of<AuthProvider>(context);
    final theme = Theme.of(context);

    return Scaffold(
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            color: auth.isOwner ? Colors.blue.shade50 : Colors.orange.shade50,
            child: Row(
              children: [
                Icon(
                  auth.isOwner ? Icons.security : Icons.lock,
                  color: auth.isOwner ? Colors.blue.shade800 : Colors.orange.shade800,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    auth.isOwner
                        ? 'Owner View: Full customer information and revenue are visible.'
                        : 'Developer View: Customer names, contacts, and revenue are masked/ciphertext for data privacy.',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: auth.isOwner ? Colors.blue.shade900 : Colors.orange.shade900,
                    ),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _customers.isEmpty
                    ? const Center(child: Text('No customers found'))
                    : RefreshIndicator(
                        onRefresh: _loadCustomers,
                        child: ListView.builder(
                          itemCount: _customers.length,
                          itemBuilder: (context, index) {
                            final customer = _customers[index];
                            return Card(
                              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                              child: ListTile(
                                leading: CircleAvatar(
                                  backgroundColor: customer.isMasked ? Colors.grey.shade300 : Colors.blue.shade100,
                                  child: Icon(
                                    customer.isMasked ? Icons.lock_outline : Icons.business,
                                    color: customer.isMasked ? Colors.grey.shade700 : Colors.blue.shade800,
                                  ),
                                ),
                                title: Text(
                                  customer.name,
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: customer.isMasked ? Colors.grey.shade600 : Colors.black87,
                                  ),
                                ),
                                subtitle: Text('Contact: ${customer.contact}'),
                                trailing: Text(
                                  customer.isMasked ? '🔒 Masked' : '฿${customer.revenue.toStringAsFixed(0)}',
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: customer.isMasked ? Colors.grey : Colors.green.shade800,
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}
