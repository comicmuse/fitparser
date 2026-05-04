import 'package:flutter/material.dart';
import '../models/run.dart';

class RunSummaryCard extends StatelessWidget {
  final Run run;
  final VoidCallback onTap;
  final String? label;

  const RunSummaryCard({required this.run, required this.onTap, this.label, super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (label != null)
                Text(label!.toUpperCase(),
                    style: const TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
              if (label != null) const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(
                    child: Text(run.name,
                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ),
                  const Icon(Icons.chevron_right, size: 18, color: Color(0xFF888888)),
                ],
              ),
              const SizedBox(height: 2),
              Text(_formatDate(run.date), style: const TextStyle(fontSize: 12, color: Color(0xFF888888))),
              const SizedBox(height: 10),
              Row(
                children: [
                  _metric('${run.distanceKm?.toStringAsFixed(1) ?? '—'} km', 'dist'),
                  _metric(run.durationFormatted, 'time'),
                  if (run.avgPowerW != null) _metric('${run.avgPowerW}W', 'power'),
                  if (run.avgHr != null) _metric('${run.avgHr}', 'HR'),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _metric(String value, String label) => Expanded(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
        Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF888888))),
      ],
    ),
  );

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]} ${dt.year}';
    } catch (_) {
      return isoDate;
    }
  }
}
