"""
Quality scoring service for podcast transcript metrics.

Converts raw quality metrics into normalized scores, ratings, and
human-readable interpretations for podcast quality assessment.

Score dimensions:
- content_length: Based on estimated duration (longer is better, up to 30 min)
- coherence: Direct mapping from coherence_score (sentence variation)
- balance: Based on is_balanced flag and speaker ratio
- engagement: Based on banter quality and dialogue turn count
- overall: Weighted average (content 20%, coherence 25%, balance 30%, engagement 25%)
"""

from typing import List
from ..schemas.quality_metrics import QualityMetricsData, QualityScore, Interpretation


def _rating_from_score(score: float) -> str:
	"""Map a 0.0-1.0 score to a rating label."""
	if score >= 0.8:
		return "excellent"
	elif score >= 0.6:
		return "good"
	elif score >= 0.4:
		return "fair"
	else:
		return "poor"


class QualityScoreService:
	"""Calculate quality scores and interpretations from raw metrics."""

	def calculate_quality_scores(self, metrics: QualityMetricsData) -> List[QualityScore]:
		"""
		Calculate quality scores across multiple dimensions.

		Args:
			metrics: Raw quality metrics from transcript analysis

		Returns:
			List of QualityScore objects for content_length, coherence,
			balance, engagement, and overall dimensions
		"""
		cl_score, cl_rating = self._calculate_content_length_score(metrics.duration_estimate_minutes)
		co_score, co_rating = self._calculate_coherence_score(metrics.coherence_score)
		ba_score, ba_rating = self._calculate_balance_score(metrics.is_balanced, metrics.speaker_balance_ratio)
		en_score, en_rating = self._calculate_engagement_score(
			metrics.has_good_banter, metrics.dialogue_turns
		)
		ov_score, ov_rating = self._calculate_overall_score(cl_score, co_score, ba_score, en_score)

		return [
			QualityScore(dimension="content_length", score=round(cl_score, 4), rating=cl_rating),
			QualityScore(dimension="coherence", score=round(co_score, 4), rating=co_rating),
			QualityScore(dimension="balance", score=round(ba_score, 4), rating=ba_rating),
			QualityScore(dimension="engagement", score=round(en_score, 4), rating=en_rating),
			QualityScore(dimension="overall", score=round(ov_score, 4), rating=ov_rating),
		]

	def generate_interpretation(
		self,
		metrics: QualityMetricsData,
		quality_scores: List[QualityScore]
	) -> Interpretation:
		"""
		Generate human-readable interpretation of metrics.

		Args:
			metrics: Raw quality metrics
			quality_scores: Calculated quality scores

		Returns:
			Interpretation with overall_rating, strengths, improvements, recommendations
		"""
		overall = next((s for s in quality_scores if s.dimension == "overall"), None)
		overall_rating = overall.rating if overall else "fair"

		strengths = self.generate_strengths(metrics)
		improvements = self.generate_improvements(metrics)

		# Produce a short recommendation based on overall rating
		if overall_rating == "excellent":
			recommendations = "Outstanding episode quality. Keep up the excellent work!"
		elif overall_rating == "good":
			recommendations = "Strong episode overall. Address the improvement areas for even better results."
		elif overall_rating == "fair":
			recommendations = "The episode has potential. Focus on the improvement areas to raise quality."
		else:
			recommendations = "Significant improvements needed. Review all improvement suggestions before publishing."

		return Interpretation(
			overall_rating=overall_rating,
			strengths=strengths,
			improvements=improvements,
			recommendations=recommendations,
		)

	def _calculate_content_length_score(self, duration_minutes: float) -> tuple[float, str]:
		"""
		Score content length based on estimated duration.

		Ranges:
		- 0-5 min: poor (0.3)
		- 5-10 min: fair (0.55)
		- 10-30 min: good (0.85)
		- 30+ min: excellent (1.0)
		"""
		if duration_minutes < 5:
			score = 0.3
		elif duration_minutes < 10:
			score = 0.55
		elif duration_minutes < 30:
			score = 0.85
		else:
			score = 1.0
		return score, _rating_from_score(score)

	def _calculate_coherence_score(self, coherence: float) -> tuple[float, str]:
		"""Direct mapping from coherence metric to score."""
		return coherence, _rating_from_score(coherence)

	def _calculate_balance_score(self, is_balanced: bool, balance_ratio: float) -> tuple[float, str]:
		"""
		Score speaker balance.

		- Balanced (ratio 0.3-3.33): 1.0 excellent
		- Near-balanced (ratio 0.25-0.4 or 2.5-4.0): 0.7 good
		- Otherwise: 0.5 fair
		"""
		if is_balanced:
			score = 1.0
		elif (0.25 <= balance_ratio <= 0.4) or (2.5 <= balance_ratio <= 4.0):
			score = 0.7
		else:
			score = 0.5
		return score, _rating_from_score(score)

	def _calculate_engagement_score(
		self,
		has_good_banter: bool,
		dialogue_turns: int,
	) -> tuple[float, str]:
		"""
		Score dialogue engagement.

		- Good banter + many turns (>50): 1.0 excellent
		- Good banter alone: 0.8 good
		- Many turns (>30) but no good banter: 0.6 good
		- Otherwise: 0.4 fair
		"""
		if has_good_banter and dialogue_turns > 50:
			score = 1.0
		elif has_good_banter:
			score = 0.8
		elif dialogue_turns > 30:
			score = 0.6
		else:
			score = 0.4
		return score, _rating_from_score(score)

	def _calculate_overall_score(
		self,
		content_score: float,
		coherence_score: float,
		balance_score: float,
		engagement_score: float,
	) -> tuple[float, str]:
		"""
		Weighted overall quality score.

		Weights: content 20%, coherence 25%, balance 30%, engagement 25%
		"""
		score = (
			content_score * 0.20
			+ coherence_score * 0.25
			+ balance_score * 0.30
			+ engagement_score * 0.25
		)
		return score, _rating_from_score(score)

	def generate_strengths(self, metrics: QualityMetricsData) -> List[str]:
		"""Generate list of quality strengths from metrics."""
		strengths = []
		if metrics.is_balanced:
			strengths.append("Excellent speaker balance")
		if metrics.has_good_banter:
			strengths.append(f"Good dialogue engagement with {metrics.dialogue_turns} speaker turns")
		if metrics.coherence_score >= 0.75:
			strengths.append("Natural conversational flow and sentence variation")
		if metrics.duration_estimate_minutes >= 10:
			strengths.append(f"Good episode length ({metrics.duration_estimate_minutes:.1f} minutes)")
		if metrics.max_monologue_words <= 100:
			strengths.append("Short, punchy exchanges with no long monologues")
		return strengths

	def generate_improvements(self, metrics: QualityMetricsData) -> List[str]:
		"""Generate list of improvement suggestions from metrics."""
		improvements = []
		if not metrics.is_balanced:
			improvements.append(
				f"Improve speaker balance (current ratio {metrics.speaker_balance_ratio:.2f}, "
				f"target 0.3-3.33)"
			)
		if not metrics.has_good_banter:
			if metrics.max_monologue_words > 200:
				improvements.append(
					f"Break up monologues - current max is {metrics.max_monologue_words} words "
					f"(target <=200)"
				)
			if metrics.dialogue_turns < 5:
				improvements.append(
					f"Increase dialogue turns - only {metrics.dialogue_turns} turns "
					f"(target >=5)"
				)
		if metrics.coherence_score < 0.65:
			improvements.append(
				f"Consider more varied sentence structure "
				f"(coherence {metrics.coherence_score:.2f}, target 0.65+)"
			)
		if metrics.duration_estimate_minutes < 5:
			improvements.append(
				f"Episode is quite short ({metrics.duration_estimate_minutes:.1f} min) - "
				f"consider adding more content"
			)
		return improvements
