import unittest
import numpy as np
import pandas as pd
from pipeline import budget_plan, group_split, FEATURES, top_k_metrics, validate_lookml


class BoundaryTests(unittest.TestCase):
    def test_top_selection(self):
        result = top_k_metrics([0,1,1,0,0], [.1,.9,.8,.2,.3], .4)
        self.assertEqual(result["positive_labels"],2)
        self.assertEqual(result["recall"],1)

    def test_zero_budget(self):
        result = budget_plan([.9,.8],dict(budget=0,contact_cost=2,rescue_probability_if_would_churn=.1,margin_per_saved_customer=100))
        self.assertEqual(result["selected"],0)

    def test_unprofitable_contacts(self):
        result = budget_plan([.01,.02],dict(budget=100,contact_cost=2,rescue_probability_if_would_churn=.1,margin_per_saved_customer=100))
        self.assertEqual(result["selected"],0)

    def test_cost_not_zero(self):
        with self.assertRaises(ValueError):
            budget_plan([.9],dict(budget=100,contact_cost=0,rescue_probability_if_would_churn=.1,margin_per_saved_customer=100))

    def test_budget_cap(self):
        result = budget_plan([.9]*20,dict(budget=5,contact_cost=2,rescue_probability_if_would_churn=.1,margin_per_saved_customer=100))
        self.assertEqual(result["selected"],2)
        self.assertEqual(result["contact_spend"],4)

    def test_duplicate_vectors_stay_together(self):
        frame=pd.DataFrame({col:np.repeat(np.arange(100),2) for col in FEATURES})
        frame["churn"]=np.tile([0,1],100)
        a,b,c,g=group_split(frame)
        self.assertFalse(set(g[a]) & set(g[b]))
        self.assertFalse(set(g[a]) & set(g[c]))
        self.assertFalse(set(g[b]) & set(g[c]))

    def test_semantics(self):
        self.assertEqual(validate_lookml()["files_parsed"],2)


if __name__ == "__main__":
    unittest.main()
