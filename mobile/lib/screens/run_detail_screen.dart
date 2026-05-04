import 'package:flutter/material.dart';
class RunDetailScreen extends StatelessWidget {
  final int runId;
  const RunDetailScreen({required this.runId, super.key});
  @override
  Widget build(BuildContext context) => Scaffold(body: Center(child: Text('Run $runId')));
}
