from app.ai.schemas.onboarding import PlanRecommendationData, PlanRecommendationRequest


class PlanRecommender:
    """
    Separate from ICP builder.

    This should only run when the frontend/backend explicitly asks for plan recommendation.
    """

    def recommend(self, request: PlanRecommendationRequest) -> PlanRecommendationData:
        team_size = request.team_size or 1
        searches = request.expected_monthly_company_searches or 0
        contacts = request.expected_monthly_contacts or 0
        emails = request.expected_monthly_emails or 0
        domains = request.number_of_sending_domains or 1

        if (
            request.salesforce_required
            or team_size > 50
            or searches > 50000
            or contacts > 100000
            or emails > 100000
            or domains > 20
            or request.support_required.lower() in ["dedicated", "custom", "enterprise"]
        ):
            return PlanRecommendationData(
                recommended_plan="Enterprise",
                confidence=90,
                reasons=[
                    "Your usage or integration needs appear to require a custom setup.",
                    "Enterprise is better for Salesforce, high-volume usage, custom support, or large teams.",
                ],
                next_steps=[
                    "Book a sales call.",
                    "Confirm CRM, user seats, domains, and monthly usage requirements.",
                ],
            )

        if team_size > 10 or searches > 15000 or contacts > 50000 or emails > 50000 or domains > 10:
            return PlanRecommendationData(
                recommended_plan="Scale",
                confidence=86,
                reasons=[
                    "Your expected usage is higher than a standard growth workflow.",
                    "Scale is better for larger teams and higher-volume prospecting.",
                ],
                next_steps=[
                    "Start with Scale if your team already has an active outbound motion.",
                    "Use the ICP output to prioritize high-fit segments first.",
                ],
            )

        if team_size > 3 or searches > 5000 or contacts > 10000 or emails > 10000 or domains > 3:
            return PlanRecommendationData(
                recommended_plan="Growth",
                confidence=84,
                reasons=[
                    "Your usage fits a growing team building consistent pipeline.",
                    "Growth gives more search, contact, email, domain, and seat capacity than Starter.",
                ],
                next_steps=[
                    "Start with Growth.",
                    "Use the ICP builder and ready search recipe to create your first target segment.",
                ],
            )

        return PlanRecommendationData(
            recommended_plan="Starter",
            confidence=82,
            reasons=[
                "Your usage fits a small team or early outbound workflow.",
                "Starter is suitable for testing and validating your first ICP.",
            ],
            next_steps=[
                "Start with Starter.",
                "Build your first ICP and run a focused search before scaling volume.",
            ],
        )