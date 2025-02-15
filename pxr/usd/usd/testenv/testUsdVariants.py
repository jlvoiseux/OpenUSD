#!/pxrpythonsubst
#
# Copyright 2017 Pixar
#
# Licensed under the terms set forth in the LICENSE.txt file available at
# https://openusd.org/license.

import sys, os, unittest
from pxr import Sdf, Usd, Tf

allFormats = ['usd' + x for x in 'ac']

class TestUsdVariants(unittest.TestCase):
    def test_VariantSetAPI(self):
        f = 'MilkCartonA.usda'
        layer = Sdf.Layer.FindOrOpen(f)
        self.assertTrue(layer)

        stage = Usd.Stage.Open(f)
        self.assertTrue(stage)

        prim = stage.GetPrimAtPath('/MilkCartonA')
        self.assertTrue(prim)

        self.assertTrue(prim.HasVariantSets())
        self.assertTrue('modelingVariant' in prim.GetVariantSets().GetNames())
        self.assertEqual(prim.GetVariantSet('modelingVariant').GetVariantSelection(),
                         'Carton_Opened')
        self.assertEqual(prim.GetVariantSets().GetVariantSelection('modelingVariant'),
                         'Carton_Opened')
        self.assertEqual(prim.GetVariantSet('modelingVariant').GetVariantNames(),
                         ['ALL_VARIANTS', 'Carton_Opened', 'Carton_Sealed'])
        self.assertEqual(prim.GetVariantSet('modelingVariant').GetName(),
                         'modelingVariant')
        # GetAllVariantSelections returns the union of all strongest variant
        # selection opinions, even if the variant set doesn't exist.
        self.assertEqual(prim.GetVariantSets().GetAllVariantSelections(),
                         {"modelingVariant" : "Carton_Opened", 
                          "shadingComplexity" : "full",
                          "localDanglingVariant" : "local",
                          "referencedDanglingVariant" : "ref"})
        self.assertTrue(prim.GetVariantSets().HasVariantSet(
                        "shadingComplexity"))
        self.assertFalse(prim.GetVariantSets().HasVariantSet(
                         "localDanglingVariant"))
        self.assertFalse(prim.GetVariantSets().HasVariantSet(
                         "referencedDanglingVariant"))
        # ClearVariantSelection clears the variant set selection from the edit target,
        # permitting any weaker layer selection to take effect
        stage.SetEditTarget(stage.GetSessionLayer())
        prim.GetVariantSet('modelingVariant').SetVariantSelection('Carton_Sealed')
        self.assertEqual(prim.GetVariantSet('modelingVariant').GetVariantSelection(),
                        'Carton_Sealed')
        prim.GetVariantSet('modelingVariant').ClearVariantSelection()
        self.assertEqual(prim.GetVariantSet('modelingVariant').GetVariantSelection(),
                        'Carton_Opened')
        # BlockVariantSelection sets the selection to empty, which blocks weaker variant
        # selection opinions
        prim.GetVariantSet('modelingVariant').BlockVariantSelection()
        self.assertEqual(prim.GetVariantSet('modelingVariant').GetVariantSelection(), '')

    def test_VariantSelectionPathAbstraction(self):
        for fmt in allFormats:
            s = Usd.Stage.CreateInMemory('TestVariantSelectionPathAbstraction.'+fmt)
            p = s.OverridePrim("/Foo")
            vss = p.GetVariantSets()
            self.assertFalse(p.HasVariantSets())
            vs = vss.AddVariantSet("LOD")
            self.assertTrue(p.HasVariantSets())
            self.assertTrue(vs)
            self.assertTrue(vs.AddVariant("High"))
            self.assertTrue(p.HasVariantSets())

            # This call triggers the bug. This happens because it triggers the
            # computation of a PcpPrimIndex for the variant prim, which then causes
            # the prim with a variant selection to be included in the UsdStage's
            # scene graph later when the next round of change processing occurs.
            #
            # XXX: WBN to indicate the bug # above.  This code changed when the
            # variant API changed during the switch to using EditTargets instead of
            # UsdPrimVariant.  It's unclear whether or not the mystery bug is still
            # reproduced. Leaving the test in place as much as possible..
            self.assertFalse(p.GetAttribute("bar").IsDefined())

            # This triggers change processing which will include the prim with the
            # variant selection and put it on the stage.
            vs.SetVariantSelection('High')
            editTarget = vs.GetVariantEditTarget()
            self.assertTrue(editTarget)
            with Usd.EditContext(s, editTarget):
                s.DefinePrim(p.GetPath().AppendChild('Foobar'), 'Scope')

            self.assertTrue(s.GetPrimAtPath(p.GetPath().AppendChild('Foobar')))

            # Here's the actual manifestation of the bug: We should still not have
            # this prim on the stage, but when the bug is present, we do. Paths
            # containing variant selections can never identify objects on a stage.
            # Verify that the stage does not contain a prim for the variant prim
            # spec we just created at </Foo{LOD=High}Foobar>
            testPath = p.GetPath().AppendVariantSelection(
                'LOD', 'High').AppendChild('Foobar')
            self.assertFalse(s.GetPrimAtPath(testPath))

    def test_NestedVariantSets(self):
        for fmt in allFormats:
            s = Usd.Stage.CreateInMemory('TestNestedVariantSets.'+fmt)
            p = s.DefinePrim('/Foo', 'Scope')
            vss = p.GetVariantSets()
            vs_lod = vss.AddVariantSet("LOD")
            vs_lod.AddVariant("High")
            vs_lod.SetVariantSelection('High')
            with vs_lod.GetVariantEditContext():
                # Create a directly nested variant set.
                vs_costume = vss.AddVariantSet("Costume")
                vs_costume.AddVariant("Spooky")
                vs_costume.SetVariantSelection('Spooky')
                with vs_costume.GetVariantEditContext():
                    s.DefinePrim(p.GetPath().AppendChild('SpookyHat'), 'Cone')

                # Create a child prim with its own variant set.
                p2 = s.DefinePrim(p.GetPath().AppendChild('DetailedStuff'), 'Scope')
                vss_p2 = p2.GetVariantSets()
                vs_p2 = vss_p2.AddVariantSet("StuffVariant")
                vs_p2.AddVariant("A")
                vs_p2.SetVariantSelection('A')
                with vs_p2.GetVariantEditContext():
                    s.DefinePrim(p2.GetPath().AppendChild('StuffA'), 'Sphere')

            self.assertTrue(vss.GetNames() == ['LOD', 'Costume'])
            self.assertTrue(s.GetPrimAtPath('/Foo/SpookyHat'))
            self.assertTrue(s.GetRootLayer().GetPrimAtPath(
                '/Foo{LOD=High}{Costume=Spooky}SpookyHat'))

    def test_USD_5189(self):
        for fmt in allFormats:
            l = Sdf.Layer.CreateAnonymous('.'+fmt)
            l.ImportFromString('''#usda 1.0
(
   defaultPrim = "prim"
)

def "prim" (
    inherits = </class>
    prepend variantSets = "myVariantSet"
    variants = {
        string myVariantSet = "light"
    }
)
{
    variantSet "myVariantSet" = {
        "full"
        {
            string bar = "full"
        }
        
        "light"
        {
            string bar = "light"
        }
    }
}

over "refprim" (
    references = </prim>
    delete variantSets = "myVariantSet"
    prepend variantSets = "myRefVariantSet"
)
{
    variantSet "myRefVariantSet" = {
        "open"
        {
        }
    }
}

over "refrefprim" (
    references = </refprim>
    delete variantSets = "myRefVariantSet"
    variants = {
        string myVariantSet = "full"
    }
    prepend variantSets = "myRefRefVariantSet"
)
{
    variantSet "myRefRefVariantSet" = {
        "closed"
        {
        }
    }
}
''')

            s = Usd.Stage.Open(l)
            p = s.GetPrimAtPath('/prim')
            rp = s.GetPrimAtPath('/refprim')
            rrp = s.GetPrimAtPath('/refrefprim')

            # With bug USD-5189, only the first would return 'myVariantSet', the
            # others would be empty.
            self.assertEqual(p.GetVariantSets().GetNames(),
                             ['myVariantSet'])
            self.assertEqual(rp.GetVariantSets().GetNames(),
                             ['myRefVariantSet', 'myVariantSet'])
            self.assertEqual(rrp.GetVariantSets().GetNames(),
                             ['myRefRefVariantSet', 'myRefVariantSet', 'myVariantSet'])

if __name__ == '__main__':
    unittest.main()
