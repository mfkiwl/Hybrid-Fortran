import unittest

class TestCommonTools(unittest.TestCase):
	def testTextSplittingBasic(self):
		from tools.commons import splitTextAtLeftMostOccurrence
		self.assertEqual(
			splitTextAtLeftMostOccurrence("", ""),
			("", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("abcd", ""),
			("", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("", "abcd"),
			("abcd", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "abcd"),
			("abcd", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "a bcd"),
			("", "a", " bcd")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "a bcda"),
			("", "a", " bcda")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", " bcda"),
			(" bcda", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", " bcd a"),
			(" bcd ", "a", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "bcd a123"),
			("bcd a123", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "bcd a 123"),
			("bcd ", "a", " 123")
		)

	def testTextSplittingQuoted(self):
		from tools.commons import splitTextAtLeftMostOccurrence
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "bcd \"a\" 123"),
			("bcd \"a\" 123", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "bcd \'a\' 123"),
			("bcd \'a\' 123", "", "")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "bcd \'a\'a 123"),
			("bcd \'a\'", "a", " 123")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "\'a\'a 123"),
			("\'a\'", "a", " 123")
		)
		self.assertEqual(
			splitTextAtLeftMostOccurrence("a", "bcd a\'a\'"),
			("bcd ", "a", "\'a\'")
		)
		#$$$ quotes within quotes analysis not supported for now
		# self.assertEqual(
		# 	splitTextAtLeftMostOccurrence("a", "bcd \"a\'a\'\"a"),
		# 	("bcd \"a\'a\'\"", "a", "")
		# )
		# self.assertEqual(
		# 	splitTextAtLeftMostOccurrence("a", "bcd \"a\'a\'\"a 123"),
		# 	("bcd \"a\'a\'\"", "a", " 123")
		# )
		# self.assertEqual(
		# 	splitTextAtLeftMostOccurrence("a", "bcd \"a\'a\'\" \'blub a\'a 123"),
		# 	("bcd \"a\'a\'\" \'blub a\'", "a", " 123")
		# )

class TestSymbolAlgorithms(unittest.TestCase):
	def testSymbolNamesFromDeclaration(self):
		def symbolNamesFromDeclaration(declaration):
			from models.symbol import symbolNamesFromDeclarationMatch
			from tools.patterns import RegExPatterns
			return tuple(symbolNamesFromDeclarationMatch(
				RegExPatterns.Instance().symbolDeclPattern.match(declaration)
			))
		self.assertEqual(
			symbolNamesFromDeclaration("real :: a, b, c"),
			("a", "b", "c")
		)
		self.assertEqual(
			symbolNamesFromDeclaration("real :: a(n), b, c"),
			("a", "b", "c")
		)
		self.assertEqual(
			symbolNamesFromDeclaration("integer :: n, a(n), b, c"),
			("n", "a", "b", "c")
		)
		self.assertEqual(
			symbolNamesFromDeclaration("integer :: a(n, m), b, c"),
			("a", "b", "c")
		)

if __name__ == '__main__':
	unittest.main()