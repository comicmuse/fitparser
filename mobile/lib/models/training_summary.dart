class RsbPoint {
  final String date;
  final double? rsb;
  final double? ctl;
  final double? atl;

  const RsbPoint({required this.date, this.rsb, this.ctl, this.atl});

  factory RsbPoint.fromJson(Map<String, dynamic> json) => RsbPoint(
    date: json['date'] as String,
    rsb: (json['rsb'] as num?)?.toDouble(),
    ctl: (json['ctl'] as num?)?.toDouble(),
    atl: (json['atl'] as num?)?.toDouble(),
  );
}

class CurrentRsb {
  final double? rsb;
  final double? ctl;
  final double? atl;
  final String interpretation;

  const CurrentRsb({
    this.rsb,
    this.ctl,
    this.atl,
    required this.interpretation,
  });

  factory CurrentRsb.fromJson(Map<String, dynamic> json) => CurrentRsb(
    rsb: (json['rsb'] as num?)?.toDouble(),
    ctl: (json['ctl'] as num?)?.toDouble(),
    atl: (json['atl'] as num?)?.toDouble(),
    interpretation: json['interpretation'] as String? ?? 'unknown',
  );
}

class TrainingSummary {
  final CurrentRsb currentRsb;
  final List<RsbPoint> rsbHistory;

  const TrainingSummary({required this.currentRsb, required this.rsbHistory});

  factory TrainingSummary.fromJson(Map<String, dynamic> json) =>
      TrainingSummary(
        currentRsb: CurrentRsb.fromJson(
          json['current_rsb'] as Map<String, dynamic>,
        ),
        rsbHistory: (json['rsb_history'] as List<dynamic>)
            .map((e) => RsbPoint.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
