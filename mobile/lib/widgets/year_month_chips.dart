import 'package:flutter/material.dart';

class YearMonthChips extends StatelessWidget {
  final int? selectedYear;
  final int? selectedMonth;
  final List<Map<String, int>> available;
  final void Function(int? year, int? month) onChanged;

  const YearMonthChips({
    required this.available,
    required this.selectedYear,
    required this.selectedMonth,
    required this.onChanged,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    final years = available.map((e) => e['year']!).toSet().toList()
      ..sort((a, b) => b.compareTo(a));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: years
                .map(
                  (year) => Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      label: Text('$year'),
                      selected: selectedYear == year,
                      onSelected: (_) => onChanged(year, null),
                    ),
                  ),
                )
                .toList(),
          ),
        ),
        if (selectedYear != null) ...[
          const SizedBox(height: 4),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: _monthsForYear(selectedYear!)
                  .map(
                    (month) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: Text(_monthName(month)),
                        selected: selectedMonth == month,
                        onSelected: (_) => onChanged(
                          selectedYear,
                          selectedMonth == month ? null : month,
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      ],
    );
  }

  List<int> _monthsForYear(int year) {
    return available
        .where((e) => e['year'] == year)
        .map((e) => e['month']!)
        .toList()
      ..sort((a, b) => b.compareTo(a));
  }

  String _monthName(int month) {
    const names = [
      '',
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec',
    ];
    return names[month];
  }
}
